import json
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from langchain_core.runnables import (
    RunnableLambda, 
    RunnableParallel, 
    RunnablePassthrough,
    RunnableBranch
)
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

# 기존 서비스 import
from app.services.crp_classifier.crp_classifier import crp_classifier
from app.services.favicon_service_clip_new.favicon_brand_detector_clip import detect_brand_from_favicon
from app.services.text_extractor_gemini.text_brand_extractor_gemini import extract_brand_from_text_gemini
from app.core.whitelist import check_whitelist
from app.pipeline.phishing_pipeline import domain_match, capture_and_save_result, handle_new_brand_detection
from app.core.config import settings
from app.core.logger import logger


class LangChainPhishingDetector:
    """LangChain 기반 피싱 탐지 체인"""
    
    def __init__(self):
        self.chain = self._build_chain()
        
    def _build_chain(self):
        """피싱 탐지 체인 구성 (올바른 순서)"""
        
        # 1단계: 웹 콘텐츠 수집 및 스크린샷 (이미 API에서 수행됨)
        # 2단계: 화이트리스트 확인 (최우선)
        whitelist_checker = RunnableLambda(self._check_whitelist_step).with_config({"run_name": "whitelist_check"})
        
        # 3단계: CRP 검사
        crp_analyzer = RunnableLambda(self._crp_analysis_step).with_config({"run_name": "crp_analysis"})
        
        # 4단계: 파비콘 브랜드 탐지
        favicon_analyzer = RunnableLambda(self._favicon_analysis_step).with_config({"run_name": "favicon_analysis"})
        
        # 5단계: 텍스트 브랜드 탐지 (파비콘 실패시만)
        text_analyzer = RunnableLambda(self._text_analysis_step).with_config({"run_name": "text_analysis"})
        
        # 6단계: 최종 판단
        final_decision = RunnableLambda(self._final_decision_step)
        
        # 전체 체인 구성 (올바른 순서)
        chain = (
            # 1. 화이트리스트 확인
            RunnablePassthrough.assign(whitelist_result=whitelist_checker)
            | RunnableBranch(
                # 화이트리스트면 즉시 정상 판단
                (
                    lambda x: x["whitelist_result"] is not None,
                    RunnableLambda(self._whitelist_result)
                ),
                # 화이트리스트 아니면 계속 분석
                RunnablePassthrough.assign(
                    # 2. CRP 검사
                    crp_result=crp_analyzer
                )
                | RunnablePassthrough.assign(
                    # 3. 파비콘 분석
                    favicon_result=favicon_analyzer  
                )
                | RunnableBranch(
                    # 파비콘에서 브랜드 탐지 성공시
                    (
                        lambda x: x["favicon_result"] is not None,
                        final_decision
                    ),
                    # 파비콘 실패시 텍스트 분석
                    RunnablePassthrough.assign(text_result=text_analyzer) | final_decision
                )
            )
        )
        
        return chain
    
    async def ainvoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """비동기 체인 실행"""
        try:
            logger.info(f"LangChain 피싱 탐지 시작: {inputs.get('url', 'Unknown URL')}")
            result = await self.chain.ainvoke(inputs)
            logger.info(f"LangChain 피싱 탐지 완료: {result.get('reason', 'Unknown')}")
            return result
        except Exception as e:
            logger.error(f"LangChain 피싱 탐지 오류: {e}")
            return {
                "is_phish": 0,
                "reason": f"langchain_error: {str(e)}",
                "detected_brand": None,
                "detection_time": datetime.now().isoformat(),
                "langchain_execution": True
            }
    

    
    async def _check_whitelist_step(self, inputs: Dict) -> Optional[Dict]:
        """화이트리스트 확인 단계"""
        try:
            url = inputs["url"]
            # 현재 event loop에서 실행
            return await check_whitelist(url)
        except Exception as e:
            logger.error(f"화이트리스트 확인 오류: {e}")
            return None
    
    def _crp_analysis_step(self, inputs: Dict) -> bool:
        """CRP 분류 단계"""
        try:
            url = inputs["url"]
            html = inputs["html"]
            return crp_classifier(url, html)
        except Exception as e:
            logger.error(f"CRP 분석 오류: {e}")
            return False
    
    def _favicon_analysis_step(self, inputs: Dict) -> Optional[Dict]:
        """파비콘 분석 단계"""
        try:
            favicon_b64 = inputs.get("favicon_b64", "")
            url = inputs["url"]
            
            if not favicon_b64 or not favicon_b64.strip():
                return None
                
            return detect_brand_from_favicon(favicon_b64, url, threshold=0.999)
        except Exception as e:
            logger.error(f"파비콘 분석 오류: {e}")
            return None
    
    def _text_analysis_step(self, inputs: Dict) -> Optional[Dict]:
        """텍스트 분석 단계"""
        try:
            html = inputs["html"]
            url = inputs["url"]
            return extract_brand_from_text_gemini(html, url)
        except Exception as e:
            logger.error(f"텍스트 분석 오류: {e}")
            return None
    
    # 리다이렉트 관련 함수는 제거됨 (새로운 순서에서는 사용하지 않음)
    
    async def _whitelist_result(self, inputs: Dict) -> Dict:
        """화이트리스트 결과 (4단계에서 즉시 처리)"""
        whitelist_result = inputs["whitelist_result"]
        url = inputs["url"]
        html = inputs["html"]
        favicon_b64 = inputs.get("favicon_b64", "")
        user_id = inputs.get("user_id")
        ip_address = inputs.get("ip_address")
        user_agent = inputs.get("user_agent")
        redirect_analysis = inputs.get("redirect_analysis", {})
        original_url = inputs.get("original_url")
        
        logger.info(f"화이트리스트 발견: {whitelist_result.get('brand')}")
        
        # CRP 검사도 수행 (기록용)
        crp_result = False
        try:
            crp_result = crp_classifier(url, html)
            logger.info(f"화이트리스트에서 CRP 검사 결과: {crp_result}")
        except Exception as e:
            logger.error(f"CRP 검사 실패: {e}")
        
        result = {
            "is_phish": 0,
            "reason": "whitelisted",
            "detected_brand": whitelist_result.get("brand"),
            "detection_time": datetime.now().isoformat(),
            "langchain_execution": True,
            "is_crp": crp_result,
            "crp_detected": crp_result,
            "redirect_analysis": redirect_analysis
        }
        
        # 리다이렉트 정보 추가
        if original_url and original_url != url:
            result["original_url"] = original_url
            result["final_url"] = url
        
        # 스크린샷 캡처 및 DB 저장
        try:
            result = await capture_and_save_result(
                url=url,
                html=html,
                favicon_b64=favicon_b64,
                result=result,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                save_to_db=True
            )
        except Exception as e:
            logger.error(f"스크린샷 캡처 또는 DB 저장 실패: {e}")
            result.update({
                "has_screenshot": False,
                "screenshot_base64": None,
                "detection_id": None
            })
        
        return result
    
    async def _final_decision_step(self, inputs: Dict) -> Dict:
        """최종 판단 단계 (순차적 분석 결과 기반)"""
        url = inputs["url"]
        html = inputs["html"]
        favicon_b64 = inputs.get("favicon_b64", "")
        user_id = inputs.get("user_id")
        ip_address = inputs.get("ip_address")
        user_agent = inputs.get("user_agent")
        redirect_analysis = inputs.get("redirect_analysis", {})
        original_url = inputs.get("original_url")
        
        crp_result = inputs.get("crp_result", False)
        favicon_result = inputs.get("favicon_result")
        text_result = inputs.get("text_result")
        
        # 기본 결과 구조
        result = {
            "detection_time": datetime.now().isoformat(),
            "langchain_execution": True,
            "is_crp": crp_result,
            "crp_detected": crp_result,
            "redirect_analysis": redirect_analysis
        }
        
        # 리다이렉트 정보 추가 (원본 URL과 최종 URL이 다른 경우)
        if original_url and original_url != url:
            result["original_url"] = original_url
            result["final_url"] = url
        
        # 6. 파비콘 기반 판단 (최우선)
        if favicon_result:
            detected_brand = favicon_result["name"]
            detected_domain = favicon_result["domain"]
            similarity = favicon_result.get("similarity", 0.0)
            
            logger.info(f"파비콘에서 브랜드 탐지: {detected_brand} (유사도: {similarity})")
            
            if domain_match(url, detected_domain):
                result.update({
                    "is_phish": 0,
                    "reason": "favicon_brand_domain_match",
                    "detected_brand": detected_brand,
                    "similarity": similarity
                })
            else:
                result.update({
                    "is_phish": 1,
                    "reason": "favicon_brand_domain_mismatch", 
                    "detected_brand": detected_brand,
                    "similarity": similarity
                })
        
        # 7-9. 텍스트 기반 판단 (파비콘 실패시)
        elif text_result:
            detected_brand = text_result["name"]
            detected_domain = text_result.get("domain")
            
            logger.info(f"텍스트에서 브랜드 탐지: {detected_brand}")
            
            # 8. DB에서 브랜드 확인
            from app.services.brand_service import brand_service
            db_brand_info = await brand_service.check_brand_exists(detected_brand)
            
            if db_brand_info:
                # 8. 브랜드가 DB에 있음 - 공식 도메인과 비교
                official_domain = db_brand_info["domain"]
                logger.info(f"DB에서 브랜드 발견: {detected_brand} -> {official_domain}")
                
                if domain_match(url, official_domain):
                    result.update({
                        "is_phish": 0,
                        "reason": "text_brand_domain_match",
                        "detected_brand": detected_brand
                    })
                else:
                    result.update({
                        "is_phish": 1,
                        "reason": "text_brand_domain_mismatch",
                        "detected_brand": detected_brand
                    })
            else:
                # 9. 브랜드가 DB에 없음 - 브랜드 이름으로 공식 도메인 찾기
                logger.info(f"DB에 없는 브랜드 - 공식 도메인 검색: {detected_brand}")
                
                from app.pipeline.phishing_pipeline import handle_new_brand_detection
                result_from_new_brand = await handle_new_brand_detection(
                    url=url,
                    detected_brand=detected_brand,
                    detected_domain=detected_domain,
                    similarity=None,
                    detection_method="text"
                )
                
                result.update(result_from_new_brand)
        
        # 브랜드 탐지 실패
        else:
            logger.info("브랜드 탐지 실패")
            result.update({
                "is_phish": 0,
                "reason": "no_brand_detected",
                "detected_brand": None
            })
        
        # 스크린샷 캡처 및 DB 저장 (기존 API와 동일)
        try:
            result = await capture_and_save_result(
                url=url,
                html=html,
                favicon_b64=favicon_b64,
                result=result,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                save_to_db=True
            )
        except Exception as e:
            logger.error(f"스크린샷 캡처 또는 DB 저장 실패: {e}")
            # 실패해도 기본 필드는 추가
            result.update({
                "has_screenshot": False,
                "screenshot_base64": None,
                "detection_id": None
            })
        
        return result


# 전역 체인 인스턴스 (앱 시작시 한번만 생성)
_phishing_chain = None

def get_langchain_phishing_detector() -> LangChainPhishingDetector:
    """LangChain 피싱 탐지기 싱글톤 인스턴스 반환"""
    global _phishing_chain
    if _phishing_chain is None:
        _phishing_chain = LangChainPhishingDetector()
    return _phishing_chain 