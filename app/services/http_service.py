"""
HTTP Service for handling web requests with proper session management
"""
import requests
from requests.adapters import HTTPAdapter, Retry
from typing import Optional
from bs4 import BeautifulSoup

from app.core.logger import logger

# HTTP 설정
HTTP_CONFIG = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "timeout": 30,
    "retry_attempts": 3,
    "retry_backoff": 1,
    "retry_status_codes": [500, 502, 503, 504]
}

class HTTPService:
    """Service for HTTP operations"""
    
    def __init__(self):
        self._session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a hardened session with retry logic"""
        session = requests.Session()
        
        # Set headers
        session.headers.update({
            "User-Agent": HTTP_CONFIG["user_agent"],
            "Accept-Language": "en-US,en;q=0.9",
        })
        
        # Configure retries
        retries = Retry(
            total=HTTP_CONFIG["retry_attempts"],
            backoff_factor=HTTP_CONFIG["retry_backoff"],
            status_forcelist=HTTP_CONFIG["retry_status_codes"],
            allowed_methods=frozenset(["GET", "HEAD"])
        )
        
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def get_html(self, url: str, timeout: Optional[int] = None) -> Optional[str]:
        """Get HTML content from URL"""
        if timeout is None:
            timeout = HTTP_CONFIG["timeout"]
            
        try:
            logger.debug(f"Fetching HTML from: {url}")
            response = self._session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to fetch HTML from {url}: {e}")
            return None
    
    def get_content(self, url: str, timeout: Optional[int] = None) -> Optional[bytes]:
        """Get raw content from URL"""
        if timeout is None:
            timeout = HTTP_CONFIG["timeout"]
            
        try:
            logger.debug(f"Fetching content from: {url}")
            response = self._session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to fetch content from {url}: {e}")
            return None
    
    def get_response(self, url: str, timeout: Optional[int] = None) -> Optional[requests.Response]:
        """Get full response object from URL"""
        if timeout is None:
            timeout = HTTP_CONFIG["timeout"]
            
        try:
            logger.debug(f"Fetching response from: {url}")
            response = self._session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            
            # Log if there was a redirect
            if response.history:
                logger.debug(f"Redirected from {url} to {response.url}")
                
            return response
        except Exception as e:
            logger.error(f"Failed to fetch response from {url}: {e}")
            return None
    
    def is_domain_accessible(self, domain: str) -> bool:
        """Check if a domain is accessible"""
        return self.check_domain_accessibility(domain) is not None
    
    def check_domain_accessibility(self, domain: str, original_url: str = None) -> Optional[str]:
        """
        Comprehensive domain accessibility check that tries multiple URL variants.
        Returns the working URL if found, None if all fail.
        """
        # If we have an original URL from search results, try it first
        if original_url:
            logger.info(f"Testing original URL: {original_url}")
            try:
                # Try HEAD request first
                response = self._session.head(original_url, timeout=3, allow_redirects=True)
                if response.status_code < 400:
                    logger.info(f"Original URL accessible (HEAD): {original_url}")
                    return original_url
                elif response.status_code == 403:
                    logger.info(f"Original URL exists but blocked (403): {original_url}")
                    return original_url
                else:
                    logger.warning(f"Original URL HEAD failed: {original_url} - HTTP {response.status_code}")
            except Exception as e:
                logger.warning(f"Original URL HEAD failed: {original_url} - {e}")
            
            # Try GET request if HEAD failed
            try:
                logger.info(f"Trying GET request for: {original_url}")
                response = self._session.get(original_url, timeout=3, allow_redirects=True)
                if response.status_code < 400:
                    logger.info(f"Original URL accessible (GET): {original_url}")
                    return original_url
                elif response.status_code == 403:
                    logger.info(f"Original URL exists but blocked (403): {original_url}")
                    return original_url
                else:
                    logger.warning(f"Original URL GET failed: {original_url} - HTTP {response.status_code}")
            except Exception as e:
                logger.warning(f"Original URL GET failed: {original_url} - {e}")
        
        # Generate URL variants to try
        url_variants = [
            f"https://{domain}",
            f"http://{domain}",
            f"https://www.{domain}",
            f"http://www.{domain}"
        ]
        
        logger.info(f"Testing domain accessibility for: {domain}")
        
        for url in url_variants:
            logger.info(f"Trying HEAD request: {url}")
            try:
                response = self._session.head(url, timeout=3, allow_redirects=True)
                if response.status_code < 400:
                    logger.info(f"Domain accessible via HEAD: {url}")
                    return url
                elif response.status_code == 403:
                    logger.info(f"Domain exists but blocked (403): {url}")
                    return url
                else:
                    logger.warning(f"HEAD failed: {url} - HTTP {response.status_code}")
            except Exception as e:
                logger.warning(f"HEAD failed: {url} - {e}")
            
            # Try GET request if HEAD failed
            logger.info(f"Trying GET request: {url}")
            try:
                response = self._session.get(url, timeout=3, allow_redirects=True)
                if response.status_code < 400:
                    logger.info(f"Domain accessible via GET: {url}")
                    return url
                elif response.status_code == 403:
                    logger.info(f"Domain exists but blocked (403): {url}")
                    return url
                else:
                    logger.warning(f"GET failed: {url} - HTTP {response.status_code}")
            except Exception as e:
                logger.warning(f"GET failed: {url} - {e}")
        
        logger.error(f"All methods failed for domain: {domain}")
        return None
    
    async def verify_brand_mention(self, domain: str, brand_name: str) -> bool:
        """Verify if a website mentions the given brand name"""
        try:
            # Try regular request first
            html = self.get_html(f"https://{domain}", timeout=10)
            if not html:
                return False
                
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text().lower()
            return brand_name.lower() in text
            
        except Exception as e:
            logger.error(f"Error checking brand mention for {domain}: {e}")
            return False

# Global HTTP service instance
http_service = HTTPService() 