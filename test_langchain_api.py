#!/usr/bin/env python3
"""
LangChain 기반 피싱 탐지 API 테스트 스크립트
"""

import requests
import json
import time
from typing import Dict, Any

# API 서버 설정 (필요에 따라 수정)
BASE_URL = "http://localhost:8300"
API_ENDPOINTS = {
    "langchain_full": f"{BASE_URL}/detect-v2",
    "langchain_simple": f"{BASE_URL}/check_phish_simple_v2",
    "original": f"{BASE_URL}/detect",
    "original_simple": f"{BASE_URL}/check_phish_simple"
}

# 테스트용 URL들
TEST_URLS = [
    "https://google.com",      # 정상 사이트
    "https://github.com",      # 정상 사이트  
    "https://microsoft.com",   # 정상 사이트
    # "https://example-phishing-site.com",  # 피싱 사이트 예시 (실제 테스트 시 주의)
]

def test_langchain_api(url: str, endpoint_name: str, endpoint_url: str) -> Dict[str, Any]:
    """LangChain API 테스트"""
    print(f"\n{'='*50}")
    print(f"테스트: {endpoint_name}")
    print(f"URL: {url}")
    print(f"Endpoint: {endpoint_url}")
    print(f"{'='*50}")
    
    # API 요청 데이터 준비
    if "simple" in endpoint_name:
        # 심플 API용 데이터
        payload = {"url": url}
    else:
        # 풀 API용 데이터
        payload = {
            "url": url,
            "use_manual_content": False,
            "async_mode": False
        }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        # API 호출 시간 측정
        start_time = time.time()
        response = requests.post(endpoint_url, json=payload, headers=headers, timeout=30)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        print(f"상태 코드: {response.status_code}")
        print(f"응답 시간: {response_time:.2f}초")
        
        if response.status_code == 200:
            result = response.json()
            
            # 결과 출력
            if "simple" in endpoint_name:
                result_data = result.get("result", {})
            else:
                result_data = result
            
            print(f"피싱 여부: {'피싱' if result_data.get('is_phish') == 1 else '정상'}")
            print(f"판단 근거: {result_data.get('reason', 'Unknown')}")
            print(f"탐지된 브랜드: {result_data.get('detected_brand', 'None')}")
            print(f"LangChain 실행: {result_data.get('langchain_execution', 'Unknown')}")
            print(f"캐시 사용: {result_data.get('from_cache', False)}")
            
            if result_data.get("confidence"):
                print(f"신뢰도: {result_data['confidence']:.3f}")
            
            if result_data.get("is_crp"):
                print(f"CRP 탐지: {result_data['is_crp']}")
            
            # 상세 결과 (JSON)
            print(f"\n상세 결과:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            return {
                "success": True,
                "response_time": response_time,
                "result": result_data
            }
        else:
            print(f"오류: {response.status_code}")
            print(f"응답: {response.text}")
            return {
                "success": False,
                "error": response.text,
                "response_time": response_time
            }
            
    except requests.exceptions.RequestException as e:
        print(f"요청 실패: {e}")
        return {
            "success": False,
            "error": str(e),
            "response_time": 0
        }

def compare_apis(url: str):
    """기존 API와 LangChain API 비교"""
    print(f"\n{'#'*60}")
    print(f"API 비교 테스트: {url}")
    print(f"{'#'*60}")
    
    results = {}
    
    # 각 API 테스트
    for name, endpoint in API_ENDPOINTS.items():
        results[name] = test_langchain_api(url, name, endpoint)
        time.sleep(1)  # API 호출 간격
    
    # 결과 비교
    print(f"\n{'='*60}")
    print("결과 비교")
    print(f"{'='*60}")
    
    for name, result in results.items():
        if result["success"]:
            result_data = result["result"]
            print(f"{name:15}: "
                  f"{'피싱' if result_data.get('is_phish') == 1 else '정상':4} | "
                  f"{result['response_time']:5.2f}s | "
                  f"{result_data.get('reason', 'Unknown'):25} | "
                  f"LC:{result_data.get('langchain_execution', False)}")
        else:
            print(f"{name:15}: 오류 - {result.get('error', 'Unknown')}")

def main():
    """메인 테스트 함수"""
    print("LangChain 기반 피싱 탐지 API 테스트")
    print("=" * 60)
    
    # API 서버 상태 확인
    try:
        health_response = requests.get(f"{BASE_URL}/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ API 서버 연결 성공")
        else:
            print("❌ API 서버 상태 이상")
            return
    except requests.exceptions.RequestException:
        print("❌ API 서버에 연결할 수 없습니다.")
        print(f"서버가 {BASE_URL}에서 실행 중인지 확인하세요.")
        return
    
    # 각 테스트 URL에 대해 비교 테스트 수행
    for url in TEST_URLS:
        compare_apis(url)
        print("\n" + "="*60)
        print("다음 테스트를 계속하려면 Enter를 누르세요...")
        input()

if __name__ == "__main__":
    main() 