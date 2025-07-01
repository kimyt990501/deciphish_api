from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Request, status
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional
from datetime import datetime
from app.services.detector_service import detect_phishing_base64, detect_phishing_from_url
from app.core.exceptions import PhishingDetectorException
from app.core.logger import logger
from app.pipeline.phishing_pipeline import phishing_detector_base64
from app.services.web_content_collector import get_web_collector
from app.services.phishing_detection_cache_service import phishing_cache_service
from app.services.auth_service import auth_service, UserCreate, UserLogin, TokenResponse, UserUpdate, PasswordChange
from app.core.auth_middleware import get_current_user_dep, get_current_active_user_dep, require_admin, require_user, get_optional_user_dep
from app.core.config import settings

router = APIRouter()

class PhishingDetectionRequest(BaseModel):
    url: HttpUrl = Field(..., description="분석할 URL")
    use_manual_content: bool = Field(False, description="수동으로 제공된 컨텐츠 사용 여부")
    html_content: Optional[str] = Field(None, description="수동으로 제공된 HTML 컨텐츠")
    favicon_base64: Optional[str] = Field(None, description="수동으로 제공된 파비콘 (Base64)")

class PhishingDetectionResponse(BaseModel):
    is_phish: int = Field(..., description="피싱 여부 (0: 정상, 1: 피싱)")
    reason: str = Field(..., description="판단 근거")
    detected_brand: Optional[str] = Field(None, description="탐지된 브랜드")
    confidence: Optional[float] = Field(None, description="신뢰도")
    url: str = Field(..., description="분석된 URL")
    from_cache: Optional[bool] = Field(False, description="캐시에서 조회된 결과인지 여부")
    detection_id: Optional[int] = Field(None, description="탐지 결과 테이블의 ID")
    detection_time: Optional[str] = Field(None, description="검사 완료 시간 (ISO 형식)")
    screenshot_base64: Optional[str] = Field(None, description="스크린샷 Base64 데이터")
    is_redirect: Optional[bool] = Field(False, description="리다이렉트 발생 여부")
    redirect_url: Optional[str] = Field(None, description="리다이렉트된 최종 URL")

class HealthResponse(BaseModel):
    status: str = Field(..., description="서비스 상태")
    message: str = Field(..., description="상태 메시지")

class URLRequest(BaseModel):
    url: str

class ManualDetectionRequest(BaseModel):
    url: str
    html: str
    favicon_base64: str = ""

class SimplePhishingRequest(BaseModel):
    url: HttpUrl = Field(..., description="검사할 URL")

class PhishingResponse(BaseModel):
    result: dict = Field(..., description="피싱 탐지 결과")

class RedetectionRequest(BaseModel):
    detection_id: int = Field(..., description="재검사할 탐지 결과 ID")

class DetectionResultRequest(BaseModel):
    detection_id: int = Field(..., description="조회할 탐지 결과 ID")

@router.get("/health", 
    response_model=HealthResponse,
    summary="서비스 상태 확인",
    description="피싱 탐지 API 서비스의 상태를 확인합니다.")
async def health_check():
    """서비스 상태 확인"""
    return HealthResponse(
        status="healthy",
        message="Phishing Detection API is running"
    )

@router.post("/detect", 
    response_model=PhishingDetectionResponse,
    summary="피싱 사이트 탐지",
    description="제공된 URL을 분석하여 피싱 사이트 여부를 판단합니다.")
async def detect_phishing_endpoint(request: PhishingDetectionRequest, http_request: Request, current_user: dict = get_optional_user_dep()):
    """
    피싱 사이트 탐지 API
    
    URL을 분석하여 피싱 사이트 여부를 판단합니다.
    브랜드 탐지, 도메인 매칭, 콘텐츠 분석 등을 통해 종합적으로 판단합니다.
    """
    try:
        url = str(request.url)
        
        # 사용자 정보 추출
        user_id = current_user.get("id") if current_user else None
        ip_address = http_request.client.host
        user_agent = http_request.headers.get("user-agent", "")
        
        # 캐시 확인 먼저 수행
        cached_result = await phishing_cache_service.get_cached_result(url, user_id)
        if cached_result:
            logger.info(f"캐시된 결과 반환: {url} (사용자: {user_id})")
            return PhishingDetectionResponse(**cached_result)
        
        if request.use_manual_content and request.html_content:
            # 수동 컨텐츠 사용
            result = await phishing_detector_base64(
                url=url,
                html=request.html_content,
                favicon_b64=request.favicon_base64 or "",
                brand_list=[],
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
        else:
            # 자동 컨텐츠 수집 및 탐지
            collector = get_web_collector()
            html_content, favicon_base64 = collector.collect_web_content(url)
            
            if not html_content:
                raise HTTPException(status_code=400, detail="Failed to collect web content")
            
            result = await phishing_detector_base64(
                url=url,
                html=html_content,
                favicon_b64=favicon_base64 or "",
                brand_list=[],
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
        
        # 응답 형식 맞추기
        from datetime import datetime
        response_data = {
            "is_phish": result.get("is_phish", 0),
            "reason": result.get("reason", ""),
            "detected_brand": result.get("detected_brand"),
            "confidence": result.get("similarity") or result.get("confidence"),
            "url": url,
            "from_cache": result.get("from_cache", False),
            "detection_id": result.get("detection_id"),
            "detection_time": result.get("detection_time", datetime.now().isoformat()),
            "screenshot_base64": result.get("screenshot_base64")
        }
        
        return PhishingDetectionResponse(**response_data)
        
    except PhishingDetectorException as e:
        logger.error(f"Phishing detection error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/detect-phishing/")
async def detect_phishing(request: URLRequest, http_request: Request, current_user: dict = get_optional_user_dep()):
    """URL을 기반으로 피싱 사이트 탐지 (호환성을 위한 엔드포인트)"""
    try:
        # 사용자 정보 추출 먼저
        user_id = current_user.get("id") if current_user else None
        ip_address = http_request.client.host
        user_agent = http_request.headers.get("user-agent", "")
        
        # 1. 캐시 확인 먼저
        logger.info(f"캐시 확인 중: {request.url} (사용자: {user_id})")
        cached_result = await phishing_cache_service.get_cached_result(request.url, user_id)
        if cached_result:
            logger.info(f"캐시된 결과 반환: {request.url} - {cached_result['reason']} (사용자: {user_id})")
            return cached_result
        
        logger.info(f"캐시 미스 - 웹 콘텐츠 수집 시작: {request.url}")
        
        # 2. 웹 콘텐츠 수집
        collector = get_web_collector()
        html_content, favicon_base64 = collector.collect_web_content(request.url)
        
        if not html_content:
            raise HTTPException(status_code=400, detail="Failed to collect web content")
        
        # 3. 피싱 탐지 실행 (내부에서 캐시 저장됨)
        result = await phishing_detector_base64(
            url=request.url,
            html=html_content,
            favicon_b64=favicon_base64 or "",
            brand_list=[],
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # detection_time 추가 (캐시에서 온 경우가 아니면 현재 시간)
        if not result.get("detection_time"):
            result["detection_time"] = datetime.now().isoformat()
        
        return result
        
    except Exception as e:
        logger.error(f"피싱 탐지 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")

@router.post("/detect-phishing-manual/")
async def detect_phishing_manual(request: ManualDetectionRequest):
    """수동으로 제공된 HTML과 파비콘으로 피싱 사이트 탐지"""
    try:
        # 피싱 탐지 실행
        result = await phishing_detector_base64(
            url=request.url,
            html=request.html,
            favicon_b64=request.favicon_base64,
            brand_list=[],
            user_id=None,
            ip_address=None,
            user_agent=None
        )
        
        return result
        
    except Exception as e:
        logger.error(f"수동 피싱 탐지 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Manual detection failed: {str(e)}")

@router.get("/cache/stats")
async def get_cache_stats(current_user: dict = require_admin()):
    """캐시 통계 정보 조회"""
    try:
        stats = await phishing_cache_service.get_cache_stats()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"캐시 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")

@router.post("/cache/clear-expired")
async def clear_expired_cache(background_tasks: BackgroundTasks, current_user: dict = require_admin()):
    """만료된 캐시 항목 삭제 (백그라운드 작업)"""
    try:
        background_tasks.add_task(phishing_cache_service.clear_expired_cache)
        return {
            "success": True,
            "message": "캐시 정리 작업이 백그라운드에서 시작되었습니다."
        }
    except Exception as e:
        logger.error(f"캐시 정리 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

# 검사 기록 관련 API 엔드포인트들
@router.get("/history")
async def get_detection_history(
    url: Optional[str] = Query(None, description="특정 URL 필터"),
    limit: int = Query(50, description="조회할 레코드 수 (최대 100)", le=100),
    offset: int = Query(0, description="시작 위치", ge=0),
    current_user: dict = require_admin()
):
    """
    전체 검사 기록 조회 (관리자용)
    
    전체 검사 기록을 조회하거나 특정 URL의 검사 기록을 조회할 수 있습니다.
    페이징을 지원하며 최신 순으로 정렬됩니다.
    """
    try:
        history = await phishing_cache_service.get_detection_history(url, limit, offset)
        return {
            "success": True,
            "data": history
        }
    except Exception as e:
        logger.error(f"검사 기록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get detection history: {str(e)}")

@router.get("/my-history")
async def get_my_detection_history(
    url: Optional[str] = Query(None, description="특정 URL 필터"),
    limit: int = Query(50, description="조회할 레코드 수 (최대 100)", le=100),
    offset: int = Query(0, description="시작 위치", ge=0),
    current_user: dict = get_current_active_user_dep()
):
    """
    내 검사 기록 조회 (사용자용)
    
    로그인한 사용자의 개인 검사 기록만 조회합니다.
    페이징을 지원하며 최신 순으로 정렬됩니다.
    """
    try:
        user_id = current_user.get("id")
        history = await phishing_cache_service.get_user_detection_history(user_id, url, limit, offset)
        return {
            "success": True,
            "data": history,
            "user": {
                "id": user_id,
                "username": current_user.get("username")
            }
        }
    except Exception as e:
        logger.error(f"개인 검사 기록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user detection history: {str(e)}")

@router.get("/my-statistics")
async def get_my_detection_statistics(
    days: int = Query(7, description="통계 기간 (일 단위)", ge=1, le=365),
    current_user: dict = get_current_active_user_dep()
):
    """
    내 검사 통계 조회 (사용자용)
    
    로그인한 사용자의 개인 검사 통계를 조회합니다.
    """
    try:
        user_id = current_user.get("id")
        stats = await phishing_cache_service.get_user_detection_statistics(user_id, days)
        return {
            "success": True,
            "data": stats,
            "user": {
                "id": user_id,
                "username": current_user.get("username")
            }
        }
    except Exception as e:
        logger.error(f"개인 검사 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user detection statistics: {str(e)}")

@router.get("/statistics")
async def get_detection_statistics(
    days: int = Query(7, description="통계 기간 (일 단위)", ge=1, le=365),
    current_user: dict = require_admin()
):
    """
    검사 통계 정보 조회
    
    지정된 기간 동안의 검사 통계를 조회합니다.
    전체 통계, 브랜드별 통계, 이유별 통계, 일별 통계를 포함합니다.
    """
    try:
        stats = await phishing_cache_service.get_detection_statistics(days)
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"검사 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get detection statistics: {str(e)}")

@router.get("/search")
async def search_detections(
    is_phish: Optional[int] = Query(None, description="피싱 여부 (0: 정상, 1: 피싱)"),
    detected_brand: Optional[str] = Query(None, description="탐지된 브랜드 (부분 검색)"),
    reason: Optional[str] = Query(None, description="판단 이유 (부분 검색)"),
    start_date: Optional[datetime] = Query(None, description="시작 날짜 (ISO 형식)"),
    end_date: Optional[datetime] = Query(None, description="종료 날짜 (ISO 형식)"),
    limit: int = Query(50, description="조회할 레코드 수 (최대 100)", le=100),
    offset: int = Query(0, description="시작 위치", ge=0),
    current_user: dict = require_admin()
):
    """
    검사 결과 검색
    
    다양한 조건으로 검사 결과를 검색할 수 있습니다.
    여러 필터를 조합하여 사용할 수 있으며 페이징을 지원합니다.
    """
    try:
        results = await phishing_cache_service.search_detections(
            is_phish=is_phish,
            detected_brand=detected_brand,
            reason=reason,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )
        return {
            "success": True,
            "data": results
        }
    except Exception as e:
        logger.error(f"검사 결과 검색 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search detections: {str(e)}")

@router.get("/screenshot/{detection_id}")
async def get_screenshot(
    detection_id: int,
    current_user: dict = get_optional_user_dep()
):
    """
    특정 탐지 결과의 스크린샷 조회
    
    탐지 ID를 기반으로 저장된 스크린샷을 Base64 형태로 반환합니다.
    관리자는 모든 스크린샷에 접근할 수 있고, 일반 사용자는 자신의 탐지 결과만 접근 가능합니다.
    """
    try:
        # 사용자 권한 확인
        user_id = current_user.get("id") if current_user else None
        is_admin = current_user.get("role") == "admin" if current_user else False
        
        # 스크린샷 조회
        screenshot_data = await phishing_cache_service.get_screenshot_by_detection_id(
            detection_id, user_id, is_admin
        )
        
        if not screenshot_data:
            raise HTTPException(status_code=404, detail="Screenshot not found or access denied")
        
        return {
            "success": True,
            "data": {
                "detection_id": detection_id,
                "url": screenshot_data.get("url"),
                "screenshot_base64": screenshot_data.get("screenshot_base64"),
                "detected_brand": screenshot_data.get("detected_brand"),
                "is_phish": screenshot_data.get("is_phish"),
                "created_at": screenshot_data.get("created_at")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스크린샷 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get screenshot: {str(e)}")

@router.get("/screenshot/url/{encoded_url}")
async def get_screenshot_by_url(
    encoded_url: str,
    current_user: dict = get_optional_user_dep()
):
    """
    URL로 스크린샷 조회
    
    URL을 Base64로 인코딩하여 전달하면 해당 URL의 최신 스크린샷을 반환합니다.
    관리자는 모든 스크린샷에 접근할 수 있고, 일반 사용자는 자신의 탐지 결과만 접근 가능합니다.
    """
    try:
        import base64
        
        # URL 디코딩
        try:
            url = base64.b64decode(encoded_url).decode('utf-8')
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid encoded URL")
        
        # 사용자 권한 확인
        user_id = current_user.get("id") if current_user else None
        is_admin = current_user.get("role") == "admin" if current_user else False
        
        # 스크린샷 조회
        screenshot_data = await phishing_cache_service.get_screenshot_by_url(
            url, user_id, is_admin
        )
        
        if not screenshot_data:
            raise HTTPException(status_code=404, detail="Screenshot not found or access denied")
        
        return {
            "success": True,
            "data": {
                "url": url,
                "screenshot_base64": screenshot_data.get("screenshot_base64"),
                "detected_brand": screenshot_data.get("detected_brand"),
                "is_phish": screenshot_data.get("is_phish"),
                "created_at": screenshot_data.get("created_at"),
                "detection_id": screenshot_data.get("id")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"URL 기반 스크린샷 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get screenshot by URL: {str(e)}")

@router.post("/check_phish_simple", 
    response_model=PhishingResponse,
    summary="피싱 사이트 탐지 (URL만)",
    description="""
    URL만 받아서 내부적으로 HTML을 다운로드하고 파비콘을 수집하여 피싱 사이트 여부를 판단합니다.
    
    ## 처리 과정
    1. 캐시 확인 (있으면 즉시 반환)
    2. URL에서 HTML 다운로드
    3. HTML에서 파비콘 URL 추출 및 다운로드
    4. 파비콘 기반 브랜드 탐지 (CLIP 모델)
    5. 텍스트 기반 브랜드 탐지 (Gemini LLM)
    6. 도메인 매칭 검사
    7. 결과 캐시에 저장
    
    ## 반환 값
    * is_phish: 피싱 여부 (1: 피싱, 0: 정상)
    * reason: 판단 이유
    * detected_brand: 탐지된 브랜드
    * from_cache: 캐시에서 조회된 결과인지 여부 (선택사항)
    """)
async def check_phish_simple(payload: SimplePhishingRequest, http_request: Request, current_user: dict = get_optional_user_dep()):
    try:
        url = str(payload.url)
        logger.info(f"Received simple phishing detection request for URL: {url}")
        
        # 사용자 정보 추출
        user_id = current_user.get("id") if current_user else None
        ip_address = http_request.client.host
        user_agent = http_request.headers.get("user-agent", "")
        
        # 1. 캐시 확인 먼저 (사용자별로)
        logger.info(f"캐시 확인 중: {url} (사용자: {user_id})")
        cached_result = await phishing_cache_service.get_cached_result(url, user_id)
        if cached_result:
            logger.info(f"캐시된 결과 반환: {url} - {cached_result['reason']} (사용자: {user_id})")
            return {"result": cached_result}
        
        logger.info(f"캐시 미스 - 웹 콘텐츠 수집 시작: {url}")
        
        # 2. 웹 콘텐츠 수집
        collector = get_web_collector()
        html_content, favicon_base64 = collector.collect_web_content(url)
        
        if not html_content:
            logger.error(f"Failed to collect web content for URL: {url}")
            return {"result": {
                "is_phish": 0,
                "reason": "content_collection_failed",
                "detected_brand": None,
                "error": "Failed to collect web content"
            }}
        
        # 3. 피싱 탐지 실행 (내부에서 캐시 저장됨)
        result = await phishing_detector_base64(
            url=url,
            html=html_content,
            favicon_b64=favicon_base64 or "",
            brand_list=[],
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # detection_time 추가 (캐시에서 온 경우가 아니면 현재 시간)
        if not result.get("detection_time"):
            result["detection_time"] = datetime.now().isoformat()
        
        logger.info(f"Simple detection completed for URL: {url}")
        return {"result": result}
        
    except Exception as e:
        logger.error(f"Simple detection error: {str(e)}")
        return {"result": {
            "is_phish": 0,
            "reason": "detection_error",
            "detected_brand": None,
            "error": str(e)
        }}

@router.post("/redetect", 
    response_model=PhishingDetectionResponse,
    summary="피싱 사이트 재검사",
    description="detection_id를 기반으로 해당 URL을 재검사하고 결과를 업데이트합니다.")
async def redetect_phishing(request: RedetectionRequest, http_request: Request, current_user: dict = get_optional_user_dep()):
    """
    피싱 사이트 재검사 API
    
    detection_id를 받아서 해당 URL을 다시 검사하고 결과를 업데이트합니다.
    권한: 관리자는 모든 레코드, 일반 사용자는 자신의 레코드만 재검사 가능
    """
    try:
        # 사용자 정보 추출
        user_id = current_user.get("id") if current_user else None
        is_admin = current_user.get("role") == "admin" if current_user else False
        ip_address = http_request.client.host
        user_agent = http_request.headers.get("user-agent", "")
        
        # 1. 기존 검사 결과 조회 (권한 확인 포함)
        detection_record = await phishing_cache_service.get_detection_by_id(
            request.detection_id, user_id, is_admin
        )
        
        if not detection_record:
            raise HTTPException(
                status_code=404, 
                detail="검사 결과를 찾을 수 없거나 접근 권한이 없습니다."
            )
        
        url = detection_record["url"]
        logger.info(f"재검사 시작: ID {request.detection_id}, URL {url} (사용자: {user_id})")
        
        # 2. 웹 콘텐츠 수집
        collector = get_web_collector()
        html_content, favicon_base64 = collector.collect_web_content(url)
        
        if not html_content:
            raise HTTPException(status_code=400, detail="웹 콘텐츠 수집에 실패했습니다.")
        
        # 3. 피싱 탐지 실행 (캐시 저장 없이)
        result = await phishing_detector_base64(
            url=url,
            html=html_content,
            favicon_b64=favicon_base64 or "",
            brand_list=[],
            user_id=None,  # 재검사이므로 새 레코드 생성하지 않음
            ip_address=None,
            user_agent=None,
            save_to_db=False  # 재검사이므로 새 레코드 생성하지 않음
        )
        
        # 4. 기존 레코드 업데이트
        update_success = await phishing_cache_service.update_detection_result(
            detection_id=request.detection_id,
            detection_result=result,
            html_content=html_content,
            favicon_base64=favicon_base64,
            screenshot_base64=result.get("screenshot_base64")
        )
        
        if not update_success:
            raise HTTPException(status_code=500, detail="검사 결과 업데이트에 실패했습니다.")
        
        # 5. 응답 데이터 구성
        redirect_analysis = result.get("redirect_analysis", {})
        response_data = {
            "is_phish": result.get("is_phish", 0),
            "reason": result.get("reason", ""),
            "detected_brand": result.get("detected_brand"),
            "confidence": result.get("similarity") or result.get("confidence"),
            "url": url,
            "from_cache": False,  # 재검사이므로 항상 False
            "detection_id": request.detection_id,
            "detection_time": datetime.now().isoformat(),  # 재검사 완료 시간
            "screenshot_base64": result.get("screenshot_base64"),
            "is_redirect": redirect_analysis.get("has_redirect", False),
            "redirect_url": result.get("final_url") if redirect_analysis.get("has_redirect", False) else None
        }
        
        logger.info(f"재검사 완료: ID {request.detection_id}, 결과 {result.get('reason', '')} (사용자: {user_id})")
        return PhishingDetectionResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"재검사 실패: {e}")
        raise HTTPException(status_code=500, detail=f"재검사 중 오류가 발생했습니다: {str(e)}")

@router.get("/detection/{detection_id}", 
    response_model=PhishingDetectionResponse,
    summary="검사 결과 조회",
    description="detection_id를 기반으로 저장된 검사 결과를 조회합니다.")
async def get_detection_result(detection_id: int, current_user: dict = get_optional_user_dep()):
    """
    검사 결과 조회 API
    
    detection_id를 받아서 저장된 검사 결과를 조회합니다.
    권한: 관리자는 모든 레코드, 일반 사용자는 자신의 레코드만 조회 가능
    """
    try:
        # 사용자 정보 추출
        user_id = current_user.get("id") if current_user else None
        is_admin = current_user.get("role") == "admin" if current_user else False
        
        # 검사 결과 조회 (권한 확인 포함)
        detection_record = await phishing_cache_service.get_detection_by_id(
            detection_id, user_id, is_admin
        )
        
        if not detection_record:
            if user_id is None:
                logger.warning(f"인증되지 않은 사용자가 검사 결과 조회 시도: ID {detection_id}")
                raise HTTPException(
                    status_code=401, 
                    detail="로그인이 필요합니다. 토큰이 만료되었거나 유효하지 않습니다."
                )
            else:
                logger.warning(f"권한 없는 접근 시도: 사용자 {user_id}가 검사 결과 {detection_id} 조회")
                raise HTTPException(
                    status_code=404, 
                    detail="검사 결과를 찾을 수 없거나 접근 권한이 없습니다."
                )
        
        logger.info(f"검사 결과 조회: ID {detection_id}, URL {detection_record['url']} (사용자: {user_id})")
        
        # 응답 데이터 구성
        response_data = {
            "is_phish": detection_record.get("is_phish", 0),
            "reason": detection_record.get("reason", ""),
            "detected_brand": detection_record.get("detected_brand"),
            "confidence": detection_record.get("confidence"),
            "url": detection_record.get("url"),
            "from_cache": True,  # 저장된 결과이므로 캐시로 간주
            "detection_id": detection_id,
            "detection_time": detection_record.get("created_at").isoformat() if detection_record.get("created_at") else None,
            "screenshot_base64": detection_record.get("screenshot_base64"),
            "is_redirect": detection_record.get("is_redirect", False),
            "redirect_url": detection_record.get("redirect_url")
        }
        
        return PhishingDetectionResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"검사 결과 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"검사 결과 조회 중 오류가 발생했습니다: {str(e)}")

@router.post("/detection/get", 
    response_model=PhishingDetectionResponse,
    summary="검사 결과 조회 (POST)",
    description="detection_id를 POST 방식으로 받아서 저장된 검사 결과를 조회합니다.")
async def get_detection_result_post(request: DetectionResultRequest, current_user: dict = get_optional_user_dep()):
    """
    검사 결과 조회 API (POST 방식)
    
    detection_id를 POST 방식으로 받아서 저장된 검사 결과를 조회합니다.
    권한: 관리자는 모든 레코드, 일반 사용자는 자신의 레코드만 조회 가능
    """
    try:
        # 사용자 정보 추출
        user_id = current_user.get("id") if current_user else None
        is_admin = current_user.get("role") == "admin" if current_user else False
        
        # 검사 결과 조회 (권한 확인 포함)
        detection_record = await phishing_cache_service.get_detection_by_id(
            request.detection_id, user_id, is_admin
        )
        
        if not detection_record:
            raise HTTPException(
                status_code=404, 
                detail="검사 결과를 찾을 수 없거나 접근 권한이 없습니다."
            )
        
        logger.info(f"검사 결과 조회 (POST): ID {request.detection_id}, URL {detection_record['url']} (사용자: {user_id})")
        
        # 응답 데이터 구성
        response_data = {
            "is_phish": detection_record.get("is_phish", 0),
            "reason": detection_record.get("reason", ""),
            "detected_brand": detection_record.get("detected_brand"),
            "confidence": detection_record.get("confidence"),
            "url": detection_record.get("url"),
            "from_cache": True,  # 저장된 결과이므로 캐시로 간주
            "detection_id": request.detection_id,
            "detection_time": detection_record.get("created_at").isoformat() if detection_record.get("created_at") else None,
            "screenshot_base64": detection_record.get("screenshot_base64"),
            "is_redirect": detection_record.get("is_redirect", False),
            "redirect_url": detection_record.get("redirect_url")
        }
        
        return PhishingDetectionResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"검사 결과 조회 실패 (POST): {e}")
        raise HTTPException(status_code=500, detail=f"검사 결과 조회 중 오류가 발생했습니다: {str(e)}")

# 사용자 인증 관련 엔드포인트들
@router.post("/auth/register", 
    response_model=TokenResponse,
    summary="회원가입",
    description="새 사용자 계정을 생성합니다.")
async def register(user_data: UserCreate, request: Request):
    """
    회원가입 API
    
    새 사용자 계정을 생성하고 JWT 토큰을 반환합니다.
    """
    try:
        # 사용자 생성
        user = await auth_service.create_user(user_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 존재하는 사용자명 또는 이메일입니다"
            )
        
        # 자동 로그인
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")
        
        token_response = await auth_service.login(
            user_data.username, 
            user_data.password, 
            client_ip, 
            user_agent
        )
        
        if not token_response:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="계정 생성 후 로그인에 실패했습니다"
            )
        
        logger.info(f"새 사용자 등록됨: {user_data.username}")
        return token_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"회원가입 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="회원가입 중 오류가 발생했습니다"
        )

@router.post("/auth/login", 
    response_model=TokenResponse,
    summary="로그인",
    description="사용자 인증 후 JWT 토큰을 발급합니다.")
async def login(user_login: UserLogin, request: Request):
    """
    로그인 API
    
    사용자명과 비밀번호로 인증하고 JWT 토큰을 반환합니다.
    """
    try:
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")
        
        token_response = await auth_service.login(
            user_login.username, 
            user_login.password, 
            client_ip, 
            user_agent
        )
        
        if not token_response:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="잘못된 사용자명 또는 비밀번호입니다",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"사용자 로그인: {user_login.username}")
        return token_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"로그인 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="로그인 중 오류가 발생했습니다"
        )

@router.post("/auth/refresh",
    summary="토큰 갱신",
    description="리프레시 토큰으로 새 액세스 토큰을 발급받습니다.")
async def refresh_token(refresh_token: str):
    """
    토큰 갱신 API
    
    리프레시 토큰을 사용하여 새 액세스 토큰을 발급받습니다.
    """
    try:
        new_access_token = await auth_service.refresh_access_token(refresh_token)
        
        if not new_access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 리프레시 토큰입니다",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"토큰 갱신 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="토큰 갱신 중 오류가 발생했습니다"
        )

@router.post("/auth/logout",
    summary="로그아웃",
    description="현재 세션을 무효화합니다.")
async def logout(refresh_token: str):
    """
    로그아웃 API
    
    리프레시 토큰을 무효화하여 세션을 종료합니다.
    """
    try:
        success = await auth_service.revoke_session(refresh_token)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="로그아웃에 실패했습니다"
            )
        
        return {"message": "성공적으로 로그아웃되었습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"로그아웃 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="로그아웃 중 오류가 발생했습니다"
        )

@router.get("/auth/me",
    summary="내 정보 조회",
    description="현재 로그인된 사용자의 정보를 조회합니다.")
async def get_current_user_info(current_user: dict = get_current_active_user_dep()):
    """
    현재 사용자 정보 조회
    
    JWT 토큰을 기반으로 현재 로그인된 사용자의 정보를 반환합니다.
    """
    return {
        "user": current_user,
        "message": "사용자 정보 조회 성공"
    }

@router.get("/auth/admin-only",
    summary="관리자 전용 엔드포인트",
    description="관리자만 접근 가능한 테스트 엔드포인트입니다.")
async def admin_only(current_user: dict = require_admin()):
    """
    관리자 전용 엔드포인트
    
    관리자 권한이 있는 사용자만 접근할 수 있습니다.
    """
    return {
        "message": "관리자 권한 확인됨",
        "user": current_user
    }

@router.put("/auth/change-password",
    summary="비밀번호 변경",
    description="현재 비밀번호를 확인 후 새 비밀번호로 변경합니다.")
async def change_password(
    password_data: PasswordChange,
    current_user: dict = get_current_active_user_dep()
):
    """
    비밀번호 변경 API
    
    현재 비밀번호를 확인한 후 새 비밀번호로 변경합니다.
    """
    try:
        success = await auth_service.change_password(
            user_id=current_user["id"],
            current_password=password_data.current_password,
            new_password=password_data.new_password
        )
        
        if success:
            return {
                "message": "비밀번호가 성공적으로 변경되었습니다.",
                "success": True
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 비밀번호가 올바르지 않습니다."
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"비밀번호 변경 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="비밀번호 변경 중 오류가 발생했습니다."
        )

@router.put("/auth/update-profile",
    summary="개인정보 수정",
    description="사용자의 개인정보(이름, 이메일)를 수정합니다.")
async def update_profile(
    user_data: UserUpdate,
    current_user: dict = get_current_active_user_dep()
):
    """
    개인정보 수정 API
    
    사용자의 이름과 이메일을 수정합니다.
    """
    try:
        updated_user = await auth_service.update_user_info(
            user_id=current_user["id"],
            user_data=user_data
        )
        
        if updated_user:
            return {
                "message": "개인정보가 성공적으로 수정되었습니다.",
                "success": True,
                "user": {
                    "id": updated_user["id"],
                    "username": updated_user["username"],
                    "email": updated_user["email"],
                    "full_name": updated_user["full_name"],
                    "role": updated_user["role"]
                }
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="개인정보 수정에 실패했습니다. 이메일이 이미 사용 중일 수 있습니다."
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"개인정보 수정 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="개인정보 수정 중 오류가 발생했습니다."
        )

@router.delete("/auth/deactivate",
    summary="계정 비활성화",
    description="현재 사용자의 계정을 비활성화합니다.")
async def deactivate_account(current_user: dict = get_current_active_user_dep()):
    """
    계정 비활성화 API
    
    현재 로그인된 사용자의 계정을 비활성화합니다.
    """
    try:
        success = await auth_service.deactivate_user(current_user["id"])
        
        if success:
            return {
                "message": "계정이 성공적으로 비활성화되었습니다.",
                "success": True
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="계정 비활성화에 실패했습니다."
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"계정 비활성화 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="계정 비활성화 중 오류가 발생했습니다."
        )