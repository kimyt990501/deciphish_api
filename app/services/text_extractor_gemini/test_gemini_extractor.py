#!/usr/bin/env python3
"""
Gemini 텍스트 브랜드 추출기 테스트 스크립트
"""

import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.services.text_extractor_gemini import infer_brand_gemini_generate

def test_gemini_extractor():
    """Gemini 추출기 테스트"""
    
    # 테스트 URL들
    test_urls = [
        "https://www.naver.com",
        "https://www.google.com", 
        "https://www.apple.com",
        "https://www.microsoft.com"
    ]
    
    print("=== Gemini 텍스트 브랜드 추출기 테스트 ===\n")
    
    for url in test_urls:
        print(f"테스트 URL: {url}")
        try:
            result = infer_brand_gemini_generate(url)
            print(f"결과: {result}")
        except Exception as e:
            print(f"오류: {e}")
        print("-" * 50)

if __name__ == "__main__":
    test_gemini_extractor() 