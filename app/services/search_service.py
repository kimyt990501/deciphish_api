"""
Search Service for handling domain search operations
"""
import time
import tldextract
from urllib.parse import urlparse
from typing import List, Optional

from app.core.logger import logger
from app.services.http_service import http_service

# 검색 설정
SEARCH_CONFIG = {
    "max_results": 10,
    "exact_match_score": 100,
    "subdomain_score": 80
}

class SearchService:
    """Service for domain search operations"""

    def find_best_domain(self, brand_name: str) -> Optional[str]:
        logger.info(f"Starting domain search for brand: {brand_name}")
        
        # 간단한 도메인 생성 시도 (최대 6개로 제한)
        simple_domains = self._generate_simple_domains(brand_name)[:6]
        for i, domain in enumerate(simple_domains, 1):
            logger.info(f"도메인 시도 {i}/{len(simple_domains)}: {domain}")
            if http_service.check_domain_accessibility(domain):
                logger.info(f"Found working domain: {domain}")
                return domain
        
        logger.warning(f"간단한 도메인 생성으로 찾지 못함. 검색 엔진 시도...")
        
        # DuckDuckGo 검색 시도 (Google 대신) - 시간 제한
        try:
            logger.info(f"Trying DuckDuckGo search for: {brand_name}")
            results = self._search_with_duckduckgo(brand_name)
            
            if not results:
                logger.warning("DuckDuckGo search failed - 브랜드명만으로 저장")
                return None

            self._log_search_results(results)

            exact_match = self._find_exact_match(results, brand_name)
            if exact_match:
                return exact_match

            logger.info("Looking for best match in top 3 results...")  # 5개에서 3개로 축소
            best_match = self._find_best_match_from_top3(results, brand_name)
            if best_match:
                return best_match

        except Exception as e:
            logger.error(f"검색 중 오류 발생: {e}")
        
        logger.warning("도메인을 찾을 수 없어 브랜드명만 저장")
        return None

    def _generate_simple_domains(self, brand_name: str) -> List[str]:
        """간단한 도메인 생성 (브랜드 원산지 고려)"""
        normalized_brand = self._normalize_brand_for_domain(brand_name)
        
        # 일본 브랜드 패턴 감지
        japanese_brands = [
            'ntt', 'docomo', 'nttdocomo', 'softbank', 'sony', 'nintendo', 
            'toyota', 'honda', 'nissan', 'panasonic', 'toshiba', 'hitachi',
            'canon', 'nikon', 'mitsubishi', 'fujitsu', 'sharp', 'casio',
            'yamaha', 'mazda', 'subaru', 'suzuki', 'kawasaki', 'bandai',
            'sega', 'capcom', 'konami', 'square', 'enix', 'squareenix',
            'rakuten', 'uniqlo', 'muji', 'asics', 'mizuno', 'onitsuka'
        ]
        
        is_japanese = any(jp_brand in brand_name.lower() for jp_brand in japanese_brands)
        
        if is_japanese:
            # 일본 브랜드의 경우 .co.jp, .ne.jp 우선 시도
            common_tlds = ['.co.jp', '.ne.jp', '.jp', '.com', '.net', '.org']
            logger.info(f"일본 브랜드로 감지됨: {brand_name} - .co.jp 도메인 우선 시도")
        else:
            # 일반적인 경우
            common_tlds = ['.com', '.co.kr', '.net', '.org', '.co.uk', '.de', '.fr', '.jp']
        
        domains = []
        for tld in common_tlds:
            domains.append(f"{normalized_brand}{tld}")
        
        return domains

    def _search_with_duckduckgo(self, brand_name: str) -> List[str]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                return [r["href"] for r in ddgs.text(f"{brand_name} Official Site", max_results=SEARCH_CONFIG["max_results"])]
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []

    def _search_with_google(self, brand_name: str) -> List[str]:
        try:
            from googlesearch import search
            return list(search(f"{brand_name} Official Site", num_results=SEARCH_CONFIG["max_results"]))
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return []

    def _search_just_brand_name(self, brand_name: str) -> List[str]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                return [r["href"] for r in ddgs.text(brand_name, max_results=SEARCH_CONFIG["max_results"])]
        except Exception as e:
            logger.error(f"DuckDuckGo brand name search error: {e}")
            return []

    def _search_just_brand_name_google(self, brand_name: str) -> List[str]:
        try:
            from googlesearch import search
            return list(search(brand_name, num_results=SEARCH_CONFIG["max_results"]))
        except Exception as e:
            logger.error(f"Google brand name search error: {e}")
            return []

    def _log_search_results(self, results: List[str]):
        logger.info(f"Found {len(results)} search results:")
        for i, url in enumerate(results, 1):
            domain = self._extract_domain(url)
            logger.info(f"  {i:2d}. {url}")
            if domain:
                logger.info(f"      → Domain: {domain}")

    def _normalize_brand_for_domain(self, brand: str) -> str:
        return ''.join(c for c in brand.lower() if c.isalnum())

    def _find_exact_match(self, urls: List[str], brand_name: str) -> Optional[str]:
        normalized_brand = self._normalize_brand_for_domain(brand_name)
        for url in urls:
            domain = self._extract_domain(url)
            if not domain:
                continue
            ext = tldextract.extract(domain)
            domain_main = ext.domain.lower()
            if domain_main == normalized_brand:
                working_url = http_service.check_domain_accessibility(domain, url)
                if working_url:
                    logger.info(f"Found exact match: {domain} (via {working_url})")
                    return domain
                else:
                    logger.warning(f"Exact match {domain} is not accessible")
        return None

    def _find_best_match_from_top5(self, urls: List[str], brand_name: str) -> Optional[str]:
        best_score = 0
        best_domain = None
        best_url = None

        for url in urls[:5]:
            domain = self._extract_domain(url)
            if not domain:
                continue
            score = self._score_domain_match(domain, brand_name)
            if score == 0:
                continue
            if score > best_score:
                working_url = http_service.check_domain_accessibility(domain, url)
                if working_url:
                    best_score = score
                    best_domain = domain
                    best_url = working_url
                else:
                    logger.warning(f"Domain {domain} is not accessible")

        if best_domain:
            logger.info(f"Selected best domain: {best_domain} (score: {best_score}/100, via {best_url})")
            return best_domain
        return None

    def _find_best_match_from_top3(self, urls: List[str], brand_name: str) -> Optional[str]:
        """상위 3개 결과에서 최적 도메인 찾기 (빠른 처리용)"""
        best_score = 0
        best_domain = None
        best_url = None

        for i, url in enumerate(urls[:3], 1):
            logger.info(f"검색 결과 {i}/3 확인 중: {url}")
            domain = self._extract_domain(url)
            if not domain:
                continue
            score = self._score_domain_match(domain, brand_name)
            if score == 0:
                continue
            if score > best_score:
                working_url = http_service.check_domain_accessibility(domain, url)
                if working_url:
                    best_score = score
                    best_domain = domain
                    best_url = working_url
                    logger.info(f"유효한 도메인 발견: {best_domain}")
                else:
                    logger.warning(f"Domain {domain} is not accessible")

        if best_domain:
            logger.info(f"Selected best domain: {best_domain} (score: {best_score}/100, via {best_url})")
            return best_domain
        return None

    def _extract_domain(self, url: str) -> Optional[str]:
        try:
            ext = tldextract.extract(url)
            return f"{ext.domain}.{ext.suffix}" if ext.suffix else None
        except Exception:
            return None

    def _normalize_url(self, url: str) -> str:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith('www.') else host

    def _score_domain_match(self, domain: str, brand_name: str) -> int:
        domain = domain.lower()
        brand = brand_name.lower()
        try:
            ext = tldextract.extract(domain)
            if not ext.suffix:
                return 0

            domain_name = ext.domain
            subdomain = ext.subdomain

            if domain_name == brand:
                return SEARCH_CONFIG["exact_match_score"]
            elif domain_name == brand and subdomain and '.' not in subdomain:
                return SEARCH_CONFIG["subdomain_score"]

            return 0
        except Exception:
            return 0 