import requests
from bs4 import BeautifulSoup
import base64
from typing import Dict, Optional, Tuple, List
from urllib.parse import urljoin, urlparse
import re
import hashlib
from io import BytesIO
from PIL import Image
from app.core.logger import logger
import random
import time

class WebContentCollector:
    def __init__(self, timeout: int = 10, max_redirects: int = 5):
        """
        웹 콘텐츠 수집기 초기화
        
        Args:
            timeout: 요청 타임아웃 (초)
            max_redirects: 최대 리다이렉트 횟수
        """
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.session = requests.Session()
        self.session.max_redirects = max_redirects
        self._seen_hashes: set = set()
        
        # 다양한 User-Agent 설정 (더 많은 옵션 추가)
        self.user_agents = [
            # 최신 브라우저들
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            # 추가 User-Agent들
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
            # 오래된 브라우저들 (봇 감지 우회용)
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36",
            "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/601.1.56 (KHTML, like Gecko) Version/9.0 Safari/601.1",
            "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:54.0) Gecko/20100101 Firefox/54.0"
        ]
        
        # 기본 헤더 설정 (더 완전한 브라우저 헤더)
        self.base_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }
        
        # 오래된 브라우저용 헤더 (봇 감지 우회용)
        self.legacy_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
    
    def _get_random_user_agent(self) -> str:
        """랜덤 User-Agent 반환"""
        return random.choice(self.user_agents)
    
    def _is_legacy_browser(self, user_agent: str) -> bool:
        """오래된 브라우저인지 확인"""
        legacy_indicators = [
            "Chrome/6", "Chrome/5", "Chrome/5", "Chrome/5", "Chrome/5",
            "Firefox/5", "Firefox/5", "Firefox/5", "Firefox/5", "Firefox/5",
            "Safari/60", "Safari/60", "Safari/60", "Safari/60", "Safari/60"
        ]
        return any(indicator in user_agent for indicator in legacy_indicators)
    
    def _get_headers(self) -> Dict[str, str]:
        """현재 요청용 헤더 반환"""
        user_agent = self._get_random_user_agent()
        
        if self._is_legacy_browser(user_agent):
            headers = self.legacy_headers.copy()
        else:
            headers = self.base_headers.copy()
        
        headers["User-Agent"] = user_agent
        return headers
    
    def download_html(self, url: str) -> Optional[str]:
        """
        URL에서 HTML 다운로드 (강화된 재시도 로직)
        
        Args:
            url: 다운로드할 URL
            
        Returns:
            HTML 문자열 또는 None
        """
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Downloading HTML from: {url} (attempt {attempt + 1}/{max_retries})")
                
                # 헤더 설정
                headers = self._get_headers()
                
                # 요청 전송
                response = self.session.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                
                # 인코딩 설정
                response.encoding = response.apparent_encoding
                
                html_content = response.text
                logger.info(f"Successfully downloaded HTML ({len(html_content)} characters)")
                return html_content
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden for {url} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 지수 백오프
                        continue
                    else:
                        logger.error(f"All retry attempts failed for {url}: 403 Forbidden")
                        return None
                else:
                    logger.error(f"HTTP error downloading HTML from {url}: {e}")
                    return None
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error downloading HTML from {url} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"All retry attempts failed for {url}")
                    return None
            except Exception as e:
                logger.error(f"Unexpected error downloading HTML from {url}: {e}")
                return None
        
        return None
        try:
            logger.info(f"Downloading HTML from: {url}")
            
            # 헤더 설정
            headers = self._get_headers()
            
            # 요청 전송
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            # 인코딩 설정
            response.encoding = response.apparent_encoding
            
            html_content = response.text
            logger.info(f"Successfully downloaded HTML ({len(html_content)} characters)")
            return html_content
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.warning(f"403 Forbidden for {url}, trying with different User-Agent")
                # 다른 User-Agent로 재시도
                try:
                    headers = self._get_headers()
                    response = self.session.get(url, headers=headers, timeout=self.timeout)
                    response.raise_for_status()
                    response.encoding = response.apparent_encoding
                    html_content = response.text
                    logger.info(f"Successfully downloaded HTML with retry ({len(html_content)} characters)")
                    return html_content
                except Exception as retry_e:
                    logger.error(f"Retry failed for {url}: {retry_e}")
                    return None
            else:
                logger.error(f"HTTP error downloading HTML from {url}: {e}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download HTML from {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading HTML from {url}: {e}")
            return None
    
    def _extract_favicon_links(self, html: str, base_url: str) -> List[Tuple[str, int]]:
        """
        HTML에서 favicon 링크 추출 (우선순위 점수 시스템)
        
        Args:
            html: HTML 문자열
            base_url: 기본 URL
            
        Returns:
            (favicon_url, score) 튜플 리스트
        """
        soup = BeautifulSoup(html, "html.parser")
        candidates = []
        
        logger.info(f"Parsing HTML for favicon candidates from: {base_url}")
        
        # 1) Direct /favicon.ico fallback (highest score)
        candidates.append((urljoin(base_url, "/favicon.ico"), 10))
        logger.debug("Added default favicon.ico candidate")
        
        # 2) <link rel=...> 태그
        link_count = 0
        for link in soup.find_all("link"):
            rel = link.get("rel", [])
            href = link.get("href")
            if not href:
                continue
                
            rel_lower = [r.lower() for r in rel] if isinstance(rel, list) else [rel.lower()]
            logger.debug(f"Found link: rel={rel_lower}, href={href}")
            
            if "shortcut icon" in rel_lower:
                score = 9
                candidates.append((urljoin(base_url, href), score))
                link_count += 1
                logger.debug(f"Added shortcut icon: {href}")
            elif "icon" in rel_lower:
                score = 8
                candidates.append((urljoin(base_url, href), score))
                link_count += 1
                logger.debug(f"Added icon: {href}")
            elif "apple-touch-icon" in rel_lower:
                score = 7
                candidates.append((urljoin(base_url, href), score))
                link_count += 1
                logger.debug(f"Added apple-touch-icon: {href}")
        
        logger.info(f"Found {link_count} favicon link tags")
        
        # 3) <meta property="og:image">, <meta name="twitter:image">
        meta_count = 0
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "").lower()
            name = meta.get("name", "").lower()
            content = meta.get("content")
            if content and (prop in ["og:image"] or name in ["twitter:image"]):
                candidates.append((urljoin(base_url, content), 3))
                meta_count += 1
                logger.debug(f"Added meta image: {content} (property={prop}, name={name})")
        
        logger.info(f"Found {meta_count} meta image tags")
        
        # 4) <img> 태그에서 logo/icon 유사한 이미지 찾기
        img_count = 0
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
                
            alt = img.get("alt", "").lower()
            cls = " ".join(img.get("class", [])).lower()
            iid = img.get("id", "").lower()
            src_l = src.lower()
            score = 0
            
            if "logo" in src_l or "icon" in src_l:
                score += 2
            if "logo" in alt or "icon" in alt:
                score += 2
            if "logo" in cls or "icon" in cls:
                score += 1
            if "logo" in iid or "icon" in iid:
                score += 1
                
            if score > 0:
                candidates.append((urljoin(base_url, src), score))
                img_count += 1
                logger.debug(f"Added logo image: {src} (score={score})")
        
        logger.info(f"Found {img_count} logo-like image tags")
        
        # 5) logo/icon 요소의 background-image
        bg_count = 0
        for elm in soup.select('[id*="logo"], [class*="logo"], [id*="icon"], [class*="icon"]'):
            style = elm.get("style", "")
            m = re.search(r"background(?:-image)?\s*:\s*url\(['\"]?([^)'\" ]+)", style)
            if m:
                candidates.append((urljoin(base_url, m.group(1)), 2))
                bg_count += 1
                logger.debug(f"Added background image: {m.group(1)}")
        
        logger.info(f"Found {bg_count} background images in logo elements")
        
        # 중복 제거하면서 순서 유지
        seen = set()
        unique_candidates = []
        for url, score in candidates:
            if url not in seen:
                seen.add(url)
                unique_candidates.append((url, score))
        
        logger.info(f"Total unique candidates: {len(unique_candidates)}")
        for i, (url, score) in enumerate(unique_candidates):
            logger.debug(f"Candidate {i+1}: {url} (score: {score})")
        
        return unique_candidates
    
    def _is_valid_image(self, content: bytes) -> bool:
        """
        콘텐츠가 유효한 이미지인지 확인
        
        Args:
            content: 이미지 바이트 데이터
            
        Returns:
            유효한 이미지 여부
        """
        try:
            # HTML 콘텐츠 체크
            if content.startswith(b'<!DOCTYPE') or content.startswith(b'<html') or b'<html' in content[:1000].lower():
                return False
            
            # PIL로 이미지 유효성 검사
            img = Image.open(BytesIO(content))
            img.verify()
            return True
        except Exception:
            return False
    
    def _get_image_hash(self, content: bytes) -> str:
        """
        이미지 콘텐츠의 해시값 반환
        
        Args:
            content: 이미지 바이트 데이터
            
        Returns:
            SHA256 해시값
        """
        return hashlib.sha256(content).hexdigest()
    
    def _is_duplicate(self, hash_str: str) -> bool:
        """
        이미지 해시가 중복인지 확인
        
        Args:
            hash_str: 이미지 해시값
            
        Returns:
            중복 여부
        """
        if hash_str in self._seen_hashes:
            return True
        self._seen_hashes.add(hash_str)
        return False
    
    def download_favicon(self, favicon_url: str) -> Optional[str]:
        """
        favicon URL에서 이미지 다운로드하여 base64로 인코딩
        
        Args:
            favicon_url: favicon URL
            
        Returns:
            base64로 인코딩된 이미지 데이터 또는 None
        """
        try:
            logger.info(f"Downloading favicon from: {favicon_url}")
            response = self.session.get(favicon_url, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            
            content = response.content
            content_type = response.headers.get("content-type", "").lower()
            
            # HTML/텍스트 콘텐츠 체크
            if any(t in content_type for t in ["html", "text"]) and "image" not in content_type:
                logger.warning(f"Text content detected: {favicon_url} ({content_type})")
                return None
            
            # HTML 콘텐츠 체크
            if b"<html" in content[:1000].lower():
                logger.warning(f"HTML content detected: {favicon_url}")
                return None
            
            # 이미지 유효성 검사
            if not self._is_valid_image(content):
                logger.warning(f"Invalid image content: {favicon_url}")
                return None
            
            # 중복 이미지 체크
            h = self._get_image_hash(content)
            if self._is_duplicate(h):
                logger.info(f"Duplicate image detected: {favicon_url}")
                return None
            
            # base64 인코딩
            base64_data = base64.b64encode(content).decode('utf-8')
            
            logger.info(f"Successfully downloaded favicon ({len(content)} bytes)")
            return base64_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download favicon from {favicon_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading favicon from {favicon_url}: {e}")
            return None
    
    def collect_favicon(self, html: str, base_url: str) -> Optional[str]:
        """
        HTML에서 favicon을 수집하여 base64로 반환
        
        Args:
            html: HTML 문자열
            base_url: 기본 URL
            
        Returns:
            base64로 인코딩된 favicon 데이터 또는 None
        """
        logger.info(f"Collecting favicon for {base_url}")
        
        favicon_candidates = self._extract_favicon_links(html, base_url)
        logger.info(f"Found {len(favicon_candidates)} favicon candidates")
        
        # 점수 순으로 정렬 (높은 점수 우선)
        favicon_candidates.sort(key=lambda x: x[1], reverse=True)
        
        for favicon_url, score in favicon_candidates:
            logger.info(f"Trying favicon candidate (score {score}): {favicon_url}")
            
            favicon_base64 = self.download_favicon(favicon_url)
            if favicon_base64:
                logger.info(f"Successfully collected favicon from: {favicon_url}")
                return favicon_base64
        
        logger.warning(f"No valid favicon found after trying {len(favicon_candidates)} candidates")
        return None
    
    def collect_web_content(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        URL에서 HTML과 favicon을 모두 수집
        
        Args:
            url: 수집할 URL
            
        Returns:
            (html_content, favicon_base64) 튜플
        """
        try:
            # HTML 다운로드
            html_content = self.download_html(url)
            if not html_content:
                return None, None
            
            # favicon 수집
            favicon_base64 = self.collect_favicon(html_content, url)
            
            return html_content, favicon_base64
            
        except Exception as e:
            logger.error(f"Error collecting web content from {url}: {e}")
            return None, None

# 전역 인스턴스
web_collector = None

def get_web_collector() -> WebContentCollector:
    """전역 웹 콘텐츠 수집기 인스턴스 반환"""
    global web_collector
    if web_collector is None:
        web_collector = WebContentCollector()
    return web_collector 