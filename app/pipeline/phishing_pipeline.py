from app.services.crp_classifier.crp_classifier import crp_classifier
from app.services.favicon_service_clip_new.favicon_brand_detector_clip import detect_brand_from_favicon
from app.services.text_extractor_ollama.text_brand_extractor_ollama import extract_brand_from_text
from app.services.text_extractor_gemini.text_brand_extractor_gemini import extract_brand_from_text_gemini
from app.core.utils import extract_domain
from app.services.brand_service import brand_service
from app.services.brand_database_service import brand_database_service
from app.services.phishing_detection_cache_service import phishing_cache_service
from app.services.http_service import http_service
from app.services.screenshot_service import screenshot_service
from app.core.whitelist import check_whitelist
import subprocess
import sys
import os

def domain_match(url: str, brand_domain: str) -> bool:
    return brand_domain in extract_domain(url)

def prepare_final_result(result: dict, original_url: str, final_url: str, 
                        redirect_analysis: dict, crp_detected: bool = False) -> dict:
    """
    최종 결과에 리다이렉트 정보와 CRP 정보를 추가하는 공통 함수
    """
    # 리다이렉트 정보 추가
    if original_url != final_url:
        result["original_url"] = original_url
        result["final_url"] = final_url
    result["redirect_analysis"] = redirect_analysis
    
    # CRP 정보 추가 (호환성을 위해 두 필드 모두 추가)
    result["crp_detected"] = crp_detected
    result["is_crp"] = crp_detected
    
    return result

async def capture_and_save_result(url: str, html: str, favicon_b64: str, result: dict, 
                                user_id: int = None, ip_address: str = None, user_agent: str = None, save_to_db: bool = True) -> dict:
    """
    스크린샷을 캡처하고 결과를 DB에 저장하는 공통 함수
    """
    screenshot_base64 = None
    
    # 스크린샷 캡처 시도
    if screenshot_service.is_screenshot_needed(url):
        print(f"스크린샷 캡처 시도: {url}")
        try:
            screenshot_base64 = await screenshot_service.capture_screenshot(url)
            if screenshot_base64:
                print(f"스크린샷 캡처 성공: {len(screenshot_base64)} 바이트")
                # 결과에 스크린샷 정보 추가
                result["has_screenshot"] = True
                result["screenshot_size"] = len(screenshot_base64)
                result["screenshot_base64"] = screenshot_base64
            else:
                print(f"스크린샷 캡처 실패: {url}")
                result["has_screenshot"] = False
        except Exception as e:
            print(f"스크린샷 캡처 중 오류: {e}")
            result["has_screenshot"] = False
    else:
        print(f"스크린샷 캡처 제외 URL: {url}")
        result["has_screenshot"] = False
    
    # DB에 저장 (스크린샷 포함)
    if save_to_db:
        detection_id = await phishing_cache_service.save_detection_result(
            url, html, favicon_b64, result, user_id, ip_address, user_agent, screenshot_base64
        )
        
        # 결과에 detection_id 추가
        if detection_id:
            result["detection_id"] = detection_id
        
        # 새로운 검사 완료 시간 추가
        from datetime import datetime
        result["detection_time"] = datetime.now().isoformat()
    else:
        # 재검사인 경우 스크린샷만 결과에 추가
        if screenshot_base64:
            result["screenshot_base64"] = screenshot_base64
    
    return result

def is_suspicious_domain(url: str) -> tuple[bool, str]:
    """
    의심스러운 도메인인지 검사합니다.
    Returns: (is_suspicious, reason)
    """
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # 의심스러운 도메인 패턴들
        suspicious_patterns = [
            # 무료 동적 DNS 서비스들
            'duckdns.org', 'ngrok.io', 'ngrok.com', 'localtunnel.me',
            'serveo.net', 'pagekite.me', 'herokuapp.com',
            # 임시/무료 도메인들
            'tk', 'ml', 'ga', 'cf', 'freenom.com',
            # 단축 URL 서비스들 (이미 확장된 후라면 의심스러움)
            'bit.ly', 'tinyurl.com', 'short.link', 't.co',
            # IP 주소
            # 숫자로만 된 도메인 (IP 주소 의심)
        ]
        
        # IP 주소 패턴 체크
        import re
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}(:\d+)?$'
        if re.match(ip_pattern, domain):
            return True, "IP 주소 사용"
        
        # 의심스러운 패턴 체크
        for pattern in suspicious_patterns:
            if pattern in domain:
                return True, f"의심스러운 도메인 패턴: {pattern}"
        
        # 무작위 문자열 패턴 체크 (예: jaergfv3)
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            subdomain = domain_parts[0]
            # 8자 이상의 무작위 문자열 패턴
            if len(subdomain) >= 6 and not any(word in subdomain.lower() for word in 
                ['www', 'mail', 'api', 'app', 'mobile', 'secure', 'login', 'admin', 'shop', 'store']):
                # 연속된 자음 또는 모음이 많은 경우
                consonants = 'bcdfghjklmnpqrstvwxyz'
                vowels = 'aeiou'
                consonant_count = sum(1 for c in subdomain.lower() if c in consonants)
                vowel_count = sum(1 for c in subdomain.lower() if c in vowels)
                
                if consonant_count > vowel_count * 2 or len(subdomain) >= 8:
                    return True, "무작위 문자열 패턴의 서브도메인"
        
        return False, ""
        
    except Exception as e:
        print(f"도메인 검사 중 오류: {e}")
        return False, ""

async def get_final_url(url: str) -> tuple[str, dict]:
    """
    리다이렉트를 따라가서 최종 URL을 반환하고 리다이렉트 정보를 분석합니다.
    Returns: (final_url, redirect_analysis)
    """
    redirect_analysis = {
        "has_redirect": False,
        "redirect_count": 0,
        "suspicious_original": False,
        "suspicious_reason": "",
        "redirect_chain": []
    }
    
    try:
        print(f"리다이렉트 확인 중: {url}")
        
        # 원본 URL 의심도 검사
        is_suspicious, reason = is_suspicious_domain(url)
        redirect_analysis["suspicious_original"] = is_suspicious
        redirect_analysis["suspicious_reason"] = reason
        
        if is_suspicious:
            print(f"원본 URL이 의심스러움: {reason}")
        
        # aiohttp를 사용한 비동기 요청 (더 간단하고 안정적)
        import aiohttp
        
        # 타임아웃과 함께 요청
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                final_url = str(response.url)
                
                # 리다이렉트 발생 여부 확인
                if final_url != url:
                    redirect_analysis["has_redirect"] = True
                    redirect_analysis["redirect_count"] = len(response.history)
                    
                    print(f"리다이렉트 탐지됨: {url} -> {final_url}")
                    print(f"리다이렉트 체인: {len(response.history)}개 단계")
                    
                    # 리다이렉트 체인 기록
                    redirect_chain = [url]
                    for resp in response.history:
                        redirect_chain.append(str(resp.url))
                    redirect_chain.append(final_url)
                    redirect_analysis["redirect_chain"] = redirect_chain
                    
                else:
                    print(f"리다이렉트 없음: {url}")
                
                print(f"최종 상태코드: {response.status}")
                return final_url, redirect_analysis
        
    except aiohttp.ClientError as e:
        print(f"네트워크 오류로 인한 리다이렉트 확인 실패: {e}")
        print(f"원본 URL 사용: {url}")
        return url, redirect_analysis
    except Exception as e:
        print(f"예상치 못한 오류로 인한 리다이렉트 확인 실패: {e}")
        print(f"원본 URL 사용: {url}")
        return url, redirect_analysis

async def run_bkb_pipeline(detected_brand: str) -> bool:
    """BKB-pipeline 실행 (main.py만 실행)"""
    try:
        # 브랜드 이름이 없으면 실행하지 않음
        if not detected_brand:
            print(f"브랜드 이름이 없어 BKB-pipeline 실행 건너뛰기")
            return False
            
        # BKB-pipeline main.py 실행 - 워크스페이스 루트의 BKB-pipeline 디렉토리 참조
        workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        bkb_main_path = os.path.join(workspace_root, "BKB-pipeline_new", "main.py")
        
        # 브랜드 이름만 전달 (도메인은 BKB-pipeline이 자체적으로 찾음)
        result = subprocess.run([sys.executable, bkb_main_path, detected_brand], 
                              capture_output=True, text=True, timeout=300)
        
        # returncode가 0이 아니어도 JSON 파일이 생성되었으면 성공으로 처리
        if result.returncode == 0:
            print(f"BKB-pipeline main.py 완료: 브랜드 {detected_brand}")
            return True
        else:
            # JSON 파일이 생성되었는지 확인
            import datetime
            today = datetime.datetime.now().strftime("%Y%m%d")
            json_file_path = os.path.join(workspace_root, "BKB-pipeline_new", "data", f"processed_brands_{today}.json")
            
            if os.path.exists(json_file_path):
                print(f"BKB-pipeline JSON 파일 생성됨: {json_file_path}")
                return True
            else:
                print(f"BKB-pipeline main.py 실행 실패: {result.stderr}")
                return False
        
    except subprocess.TimeoutExpired:
        print(f"BKB-pipeline 실행 시간 초과: 브랜드 {detected_brand}")
        return False
    except Exception as e:
        print(f"BKB-pipeline 실행 오류: {e}")
        return False

async def check_brand_and_domain_match(url: str, detected_brand: str, detected_domain: str, similarity: float = None) -> dict:
    """브랜드가 DB에 있는지 확인하고 domain match 검사"""
    try:
        # DB에서 브랜드 정보 확인
        db_brand_info = await brand_service.check_brand_exists(detected_brand)
        
        if db_brand_info:
            # DB에 브랜드가 존재하면 domain match 검사
            if domain_match(url, db_brand_info["domain"]):
                return {
                    "is_phish": 0,
                    "reason": "brand_domain_match",
                    "detected_brand": detected_brand,
                    "similarity": similarity
                }
            else:
                return {
                    "is_phish": 1,
                    "reason": "brand_domain_mismatch",
                    "detected_brand": detected_brand,
                    "similarity": similarity
                }
        else:
            # DB에 브랜드가 없으면 다음 단계로 진행
            return None
            
    except Exception as e:
        print(f"브랜드 DB 확인 실패: {e}")
        return None

async def save_new_brand_to_database(brand_name: str) -> bool:
    """새로운 브랜드를 데이터베이스에 저장"""
    try:
        success = await brand_database_service.save_brand_info(brand_name)
        if success:
            print(f"새로운 브랜드가 데이터베이스에 저장되었습니다: {brand_name}")
        else:
            print(f"브랜드 저장 실패: {brand_name}")
        return success
    except Exception as e:
        print(f"브랜드 저장 중 오류: {e}")
        return False

async def handle_new_brand_detection(url: str, detected_brand: str, detected_domain: str = None, 
                                   similarity: float = None, detection_method: str = "unknown") -> dict:
    """새로운 브랜드 탐지 처리"""
    print(f"{detection_method}에서 탐지된 새로운 브랜드: {detected_brand}")
    
    # 데이터베이스에 새로운 브랜드 저장
    save_success = await save_new_brand_to_database(detected_brand)

    # 다시 DB에서 브랜드 정보 확인 (방금 저장한 정보)
    db_brand_info = await brand_service.check_brand_exists(detected_brand)
    official_domain = db_brand_info["domain"] if db_brand_info else detected_domain
    url_domain = extract_domain(url)

    if official_domain and url_domain:
        if official_domain in url_domain:
            result = {
                "is_phish": 0,
                "reason": f"{detection_method}_new_brand_detected_and_domain_match",
                "detected_brand": detected_brand,
                "official_domain": official_domain
            }
            if similarity is not None:
                result["similarity"] = similarity
            return result
        else:
            result = {
                "is_phish": 1,
                "reason": f"{detection_method}_new_brand_detected_but_domain_mismatch",
                "detected_brand": detected_brand,
                "official_domain": official_domain
            }
            if similarity is not None:
                result["similarity"] = similarity
            return result
    else:
        result = {
            "is_phish": 0,
            "reason": f"{detection_method}_new_brand_detected_and_saved" if save_success else f"{detection_method}_new_brand_detected",
            "detected_brand": detected_brand
        }
        if similarity is not None:
            result["similarity"] = similarity
        return result

async def phishing_detector_base64(url, html, favicon_b64, brand_list, user_id=None, ip_address=None, user_agent=None, save_to_db=True):
    # 0-1. 리다이렉트 확인하여 최종 URL 얻기
    print(f"피싱 검사 시작 - 원본 URL: {url}")
    final_url, redirect_analysis = await get_final_url(url)
    original_url = url  # 원본 URL도 기록
    
    # CRP 검사 결과 변수를 미리 초기화
    crp_detected = False
    
    print(f"리다이렉트 분석 결과:")
    print(f"   has_redirect: {redirect_analysis.get('has_redirect', False)}")
    print(f"   suspicious_original: {redirect_analysis.get('suspicious_original', False)}")
    print(f"   최종 URL: {final_url}")
    
    # 의심스러운 리다이렉트 탐지 플래그 설정
    suspicious_redirect_detected = redirect_analysis["suspicious_original"] and redirect_analysis["has_redirect"]
    
    # 최종 URL로 업데이트 (이후 모든 처리는 final_url 사용)
    url = final_url
    
    # 0-2. 캐시 확인 (리다이렉트 시 원본 URL로, 아니면 최종 URL로 확인)
    cache_url = original_url if redirect_analysis.get("has_redirect", False) else url
    print(f"캐시 확인 중: {cache_url}")
    cached_result = await phishing_cache_service.get_cached_result(cache_url)
    if cached_result:
        print(f"캐시된 결과 반환: {cached_result['reason']}")
        # 리다이렉트 정보 추가
        if original_url != url:
            cached_result["original_url"] = original_url
            cached_result["final_url"] = url
            cached_result["redirect_analysis"] = redirect_analysis
        return cached_result
    
    print(f"캐시 미스 - 새로운 검사 진행: {url}")
    
    # 1. 의심스러운 리다이렉트 체크 (최우선 순위)
    if suspicious_redirect_detected:
        print(f"의심스러운 리다이렉트로 피싱 분류!")
        
        # CRP 검사도 수행 (기록용)
        try:
            crp_detected = crp_classifier(url, html)
            print(f"CRP 검사 결과: {crp_detected}")
        except Exception as e:
            print(f"CRP 검사 실패: {e}")
            crp_detected = False
        
        # 브랜드 탐지 시도 (기록용)
        detected_brand = None
        
        # 파비콘으로 브랜드 탐지 시도
        if favicon_b64 and favicon_b64.strip():
            try:
                brand_from_favicon = detect_brand_from_favicon(favicon_b64, url, threshold=0.999)
                if brand_from_favicon:
                    detected_brand = brand_from_favicon["name"]
                    print(f"의심스러운 리다이렉트에서 브랜드 탐지: {detected_brand}")
            except Exception as e:
                print(f"파비콘 브랜드 탐지 실패: {e}")
        
        # 텍스트로 브랜드 탐지 시도
        if not detected_brand:
            try:
                brand_from_text = extract_brand_from_text_gemini(html, url)
                if brand_from_text:
                    detected_brand = brand_from_text["name"]
                    print(f"의심스러운 리다이렉트에서 텍스트 브랜드 탐지: {detected_brand}")
            except Exception as e:
                print(f"텍스트 브랜드 탐지 실패: {e}")
        
        result = {
            "is_phish": 1,
            "reason": f"suspicious_redirect: {redirect_analysis['suspicious_reason']}",
            "detected_brand": detected_brand
        }
        
        result = prepare_final_result(result, original_url, url, redirect_analysis, crp_detected)
        
        # 의심스러운 리다이렉트 결과 스크린샷과 함께 저장
        result = await capture_and_save_result(url, html, favicon_b64, result, user_id, ip_address, user_agent, save_to_db)
        return result
    
    # 2. 화이트리스트 체크 (정상적인 경우에만)
    whitelist_result = await check_whitelist(url)
    whitelist_brand = whitelist_result['brand'] if whitelist_result else None
    whitelist_domain = whitelist_result['domain'] if whitelist_result else None
    
    # 화이트리스트면 판단 종료
    if whitelist_brand:
        result = {
            "is_phish": 0,
            "reason": "whitelisted",
            "detected_brand": whitelist_brand
        }
        
        # 화이트리스트여도 CRP 검사 수행 (기록용)
        result = prepare_final_result(result, original_url, url, redirect_analysis, crp_detected)
        
        # 화이트리스트 결과도 스크린샷과 함께 저장
        result = await capture_and_save_result(url, html, favicon_b64, result, user_id, ip_address, user_agent, save_to_db)
        return result

    # 2. CRP 검사 - 결과만 기록하고 판단에는 사용하지 않음
    crp_detected = False
    try:
        crp_detected = crp_classifier(url, html)
        print(f"CRP 검사 결과: {crp_detected}")
    except Exception as e:
        print(f"CRP 검사 실패: {e}")
        crp_detected = False
    
    detected_brand_name = None  # 텍스트 추출기에서 탐지된 브랜드 이름 저장
    
    # 3. 파비콘 기반 탐지 (CLIP 모델) - favicon이 있는 경우에만
    if favicon_b64 and favicon_b64.strip():
        print(f"파비콘 데이터 존재, 크기: {len(favicon_b64)} 바이트")
        brand_from_favicon = detect_brand_from_favicon(favicon_b64, url, threshold=0.999)
        print(f"파비콘 탐지 결과: {brand_from_favicon}")
        
        if brand_from_favicon:
            detected_brand = brand_from_favicon["name"]
            detected_domain = brand_from_favicon["domain"]
            similarity = brand_from_favicon.get("similarity", 0.0)
            
            print(f"파비콘에서 브랜드 탐지됨: {detected_brand} (유사도: {similarity})")
            
            # 파비콘 탐지는 DB 기반이므로 브랜드가 반드시 DB에 존재함
            # 바로 도메인 매치 검사 수행
            if domain_match(url, detected_domain):
                result = {
                    "is_phish": 0,
                    "reason": "favicon_brand_domain_match",
                    "detected_brand": detected_brand,
                    "similarity": similarity
                }
            else:
                result = {
                    "is_phish": 1,
                    "reason": "favicon_brand_domain_mismatch",
                    "detected_brand": detected_brand,
                    "similarity": similarity
                }
            
            # 리다이렉트 정보와 CRP 정보 추가
            result = prepare_final_result(result, original_url, url, redirect_analysis, crp_detected)
            
            # 결과 스크린샷과 함께 저장
            result = await capture_and_save_result(url, html, favicon_b64, result, user_id, ip_address, user_agent, save_to_db)
            return result
        else:
            print(f"파비콘에서 브랜드 탐지 실패 - 임계값 0.98 미달 또는 오류")
    else:
        print(f"파비콘이 없어 파비콘 기반 탐지 건너뛰기: {url}")

    # 4. 텍스트 기반 탐지 (Gemini LLM)
    brand_from_text = extract_brand_from_text_gemini(html, url)
    if brand_from_text:
        detected_brand = brand_from_text["name"]
        detected_domain = brand_from_text["domain"]
        detected_brand_name = detected_brand  # 브랜드 이름 저장
        
        # 브랜드 DB 확인 및 domain match 검사
        result = await check_brand_and_domain_match(url, detected_brand, detected_domain)
        if result:
            # 리다이렉트 정보와 CRP 정보 추가
            result = prepare_final_result(result, original_url, url, redirect_analysis, crp_detected)
            # 결과 스크린샷과 함께 저장
            result = await capture_and_save_result(url, html, favicon_b64, result, user_id, ip_address, user_agent, save_to_db)
            return result
        
        # DB에 브랜드가 없는 경우 새로운 브랜드로 처리
        result = await handle_new_brand_detection(url, detected_brand, detected_domain, None, "text")
        
        # 리다이렉트 정보와 CRP 정보 추가
        result = prepare_final_result(result, original_url, url, redirect_analysis, crp_detected)
        # 결과 스크린샷과 함께 저장
        result = await capture_and_save_result(url, html, favicon_b64, result, user_id, ip_address, user_agent, save_to_db)
        return result

    # 5. 아무것도 탐지되지 않음
    result = {
        "is_phish": 0,
        "reason": "no_brand_detected",
        "detected_brand": None
    }
    
    # 리다이렉트 정보와 CRP 정보 추가
    result = prepare_final_result(result, original_url, url, redirect_analysis, crp_detected)
    
    # 결과 스크린샷과 함께 저장
    result = await capture_and_save_result(url, html, favicon_b64, result, user_id, ip_address, user_agent, save_to_db)
    return result