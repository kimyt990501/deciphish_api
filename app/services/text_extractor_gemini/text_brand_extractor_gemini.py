import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, Optional, List
import sys
import os
from app.core.config import settings

# 기존 utils 모듈의 extract_domain 함수 사용
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from app.core.utils import extract_domain

class TextBrandExtractorGemini:
    def __init__(self, gemini_api_key: str = None, 
                 gemini_model: str = "gemini-2.0-flash"):
        """
        Gemini 기반 텍스트 브랜드 추출기 초기화
        
        Args:
            gemini_api_key: Gemini API 키 (환경변수에서 가져옴)
            gemini_model: 사용할 Gemini 모델명
        """
        self.gemini_api_key = gemini_api_key or settings.GEMINI_API_KEY
        self.gemini_model = gemini_model
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={self.gemini_api_key}"
        
    def clean_html(self, raw_html: str) -> str:
        """HTML 정제"""
        try:
            soup = BeautifulSoup(raw_html, "html.parser")

            # 스크립트, 스타일, noscript, iframe 제거
            for tag in soup(["script", "style", "noscript", "iframe"]):
                tag.decompose()

            # 메타 태그에서 description 추출
            meta_tags = []
            for meta in soup.find_all("meta", attrs={"name": "description"}):
                if meta.get("content"):
                    meta_tags.append(meta["content"])

            # 제목 추출
            title_text = soup.title.string.strip() if soup.title else ""
            
            # 본문 텍스트 추출 (1000자로 제한)
            body_text = soup.get_text(separator=" ", strip=True)
            body_text = body_text[:1000]

            # 텍스트 결합
            combined_text = f"Title: {title_text}\nMeta: {' '.join(meta_tags)}\nBody: {body_text}"
            return combined_text
            
        except Exception as e:
            print(f"HTML 정제 실패: {e}")
            return raw_html[:1000] if raw_html else ""

    def make_prompt(self, url: str, cleaned_html: str) -> str:
        """프롬프트 구성"""
        prompt = f"""
[Task]
You are a brand detector assistant.

Given the website URL and the HTML text of a webpage, identify which well-known brand or company the webpage is trying to imitate based on its content.
Ignore the URL domain name. Judge only based on the HTML content.

Return ONLY the brand or company name as a single word or phrase. Do NOT include any explanation, sentence, or additional text.
If you cannot confidently identify a brand, return "None".

[URL]
{url}

[HTML]
{cleaned_html}

[Answer]
"""
        return prompt

    def call_gemini_api(self, prompt_text: str) -> Optional[str]:
        """Gemini API 호출"""
        try:
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt_text
                            }
                        ]
                    }
                ]
            }

            print(f"[INFO] Sending request to Gemini API (model={self.gemini_model})...")
            response = requests.post(
                self.gemini_url, 
                json=payload, 
                headers={"Content-Type": "application/json"}, 
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            brand_answer = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            print(f"[RESULT] Predicted Brand: {brand_answer}")
            return brand_answer

        except Exception as e:
            print(f"[ERROR] Gemini API 호출 실패: {e}")
            return None

    def extract_brand_from_text(self, html: str, url: str) -> Optional[Dict]:
        """
        HTML 텍스트에서 브랜드 추출
        
        Args:
            html: 웹페이지 HTML
            url: 웹페이지 URL
            
        Returns:
            탐지된 브랜드 정보 또는 None
        """
        try:
            # HTML 정제
            cleaned_html = self.clean_html(html)
            
            # 프롬프트 생성
            prompt_text = self.make_prompt(url, cleaned_html)
            
            # Gemini API 호출
            brand_answer = self.call_gemini_api(prompt_text)
            
            if brand_answer and brand_answer.lower() != "none":
                # 브랜드 정보 반환 (도메인은 기존 함수 사용)
                return {
                    "name": brand_answer,
                    "domain": extract_domain(url),
                    "method": "gemini_text_analysis"
                }
            
            return None
            
        except Exception as e:
            print(f"텍스트 브랜드 추출 실패: {e}")
            return None

    def infer_brand_from_url(self, url: str) -> Optional[str]:
        """
        URL에서 직접 HTML을 다운로드하여 브랜드 추출
        
        Args:
            url: 분석할 웹페이지 URL
            
        Returns:
            탐지된 브랜드명 또는 None
        """
        try:
            # HTML 다운로드
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; BrandBot/1.0)"
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            raw_html = resp.text

            # 브랜드 추출
            result = self.extract_brand_from_text(raw_html, url)
            return result["name"] if result else None

        except Exception as e:
            print(f"[ERROR] Failed to process {url}: {e}")
            return None

# 전역 인스턴스
text_extractor_gemini = None

def get_text_extractor_gemini() -> TextBrandExtractorGemini:
    """전역 Gemini 텍스트 추출기 인스턴스 반환"""
    global text_extractor_gemini
    if text_extractor_gemini is None:
        text_extractor_gemini = TextBrandExtractorGemini()
    return text_extractor_gemini

def extract_brand_from_text_gemini(html: str, url: str) -> Optional[Dict]:
    """텍스트에서 브랜드 추출 (편의 함수)"""
    extractor = get_text_extractor_gemini()
    return extractor.extract_brand_from_text(html, url)

def infer_brand_gemini_generate(url: str) -> Optional[str]:
    """URL에서 브랜드 추출 (편의 함수)"""
    extractor = get_text_extractor_gemini()
    return extractor.infer_brand_from_url(url) 