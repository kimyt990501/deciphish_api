import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, Optional, List
import sys
import os

# 기존 utils 모듈의 extract_domain 함수 사용
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from app.core.utils import extract_domain

class TextBrandExtractorOllama:
    def __init__(self, ollama_url: str = "http://localhost:11434/api/generate", 
                 ollama_model: str = "llama4"):
        """
        Ollama 기반 텍스트 브랜드 추출기 초기화
        
        Args:
            ollama_url: Ollama API URL
            ollama_model: 사용할 Ollama 모델명
        """
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        
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

    def call_ollama_api(self, prompt_text: str) -> Optional[str]:
        """Ollama API 호출"""
        try:
            payload = {
                "model": self.ollama_model,
                "prompt": prompt_text,
                "stream": False
            }

            print(f"[INFO] Sending request to Ollama generate (model={self.ollama_model})...")
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()
            brand_answer = result["response"].strip()
            
            print(f"[RESULT] Predicted Brand: {brand_answer}")
            return brand_answer

        except Exception as e:
            print(f"[ERROR] Ollama API 호출 실패: {e}")
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
            
            # Ollama API 호출
            brand_answer = self.call_ollama_api(prompt_text)
            
            if brand_answer and brand_answer.lower() != "none":
                # 브랜드 정보 반환 (도메인은 기존 함수 사용)
                return {
                    "name": brand_answer,
                    "domain": extract_domain(url),
                    "method": "ollama_text_analysis"
                }
            
            return None
            
        except Exception as e:
            print(f"텍스트 브랜드 추출 실패: {e}")
            return None

# 전역 인스턴스
text_extractor = None

def get_text_extractor() -> TextBrandExtractorOllama:
    """전역 텍스트 추출기 인스턴스 반환"""
    global text_extractor
    if text_extractor is None:
        text_extractor = TextBrandExtractorOllama()
    return text_extractor

def extract_brand_from_text(html: str, url: str) -> Optional[Dict]:
    """텍스트에서 브랜드 추출 (편의 함수)"""
    extractor = get_text_extractor()
    return extractor.extract_brand_from_text(html, url) 