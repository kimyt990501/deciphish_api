import asyncio
import base64
import logging
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image

logger = logging.getLogger(__name__)

class ScreenshotService:
    """웹페이지 스크린샷 캡처 서비스"""
    
    def __init__(self):
        self.timeout = 10  # 10초 타임아웃
        self.viewport_width = 1920
        self.viewport_height = 1080
        self.screenshot_width = 800  # 저장할 스크린샷 너비
        self.screenshot_height = 600  # 저장할 스크린샷 높이
    
    async def capture_screenshot_playwright(self, url: str) -> Optional[str]:
        """
        Playwright를 사용하여 스크린샷 캡처 (추천)
        """
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                # 브라우저 실행 (headless 모드)
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-software-rasterizer',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding'
                    ]
                )
                
                page = await browser.new_page(
                    viewport={'width': self.viewport_width, 'height': self.viewport_height}
                )
                
                # 사용자 에이전트 설정
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                })
                
                # 페이지 로드 (타임아웃 설정)
                print(f"스크린샷 캡처 시작: {url}")
                await page.goto(url, timeout=self.timeout * 1000, wait_until='domcontentloaded')
                
                # 잠시 대기 (동적 콘텐츠 로딩)
                await page.wait_for_timeout(2000)
                
                # 스크린샷 캡처
                screenshot_bytes = await page.screenshot(
                    type='png',
                    full_page=False,  # 뷰포트만 캡처
                    clip={
                        'x': 0,
                        'y': 0,
                        'width': self.viewport_width,
                        'height': self.viewport_height
                    }
                )
                
                await browser.close()
                
                # 이미지 리사이즈 및 Base64 인코딩
                screenshot_base64 = await self._resize_and_encode(screenshot_bytes)
                print(f"스크린샷 캡처 완료: {url} ({len(screenshot_base64)} 바이트)")
                
                return screenshot_base64
                
        except Exception as e:
            print(f"Playwright 스크린샷 캡처 실패: {e}")
            logger.error(f"Playwright 스크린샷 캡처 실패 ({url}): {e}")
            return None
    
    async def capture_screenshot_selenium(self, url: str) -> Optional[str]:
        """
        Selenium을 사용하여 스크린샷 캡처 (대안)
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            import os
            
            # Chrome 옵션 설정
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-background-networking')
            chrome_options.add_argument('--disable-sync')
            chrome_options.add_argument('--disable-translate')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-ipc-flooding-protection')
            chrome_options.add_argument(f'--window-size={self.viewport_width},{self.viewport_height}')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Docker 환경에서 Chrome 경로 설정
            chrome_binary_path = os.environ.get('CHROME_BIN', '/usr/bin/chromium')
            if os.path.exists(chrome_binary_path):
                chrome_options.binary_location = chrome_binary_path
            
            # WebDriver 실행
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as e:
                # Chrome 드라이버가 없으면 Chromium 사용
                print(f"Chrome 드라이버 실행 실패, Chromium 시도: {e}")
                service = Service('/usr/bin/chromedriver') if os.path.exists('/usr/bin/chromedriver') else None
                driver = webdriver.Chrome(service=service, options=chrome_options) if service else webdriver.Chrome(options=chrome_options)
            
            driver.set_page_load_timeout(self.timeout)
            
            # 페이지 로드
            print(f"스크린샷 캡처 시작 (Selenium): {url}")
            driver.get(url)
            
            # 잠시 대기 (동적 콘텐츠 로딩)
            await asyncio.sleep(2)
            
            # 스크린샷 캡처
            screenshot_bytes = driver.get_screenshot_as_png()
            driver.quit()
            
            # 이미지 리사이즈 및 Base64 인코딩
            screenshot_base64 = await self._resize_and_encode(screenshot_bytes)
            print(f"스크린샷 캡처 완료 (Selenium): {url} ({len(screenshot_base64)} 바이트)")
            
            return screenshot_base64
            
        except Exception as e:
            print(f"Selenium 스크린샷 캡처 실패: {e}")
            logger.error(f"Selenium 스크린샷 캡처 실패 ({url}): {e}")
            return None
    
    async def _resize_and_encode(self, screenshot_bytes: bytes) -> str:
        """
        스크린샷 이미지를 리사이즈하고 Base64로 인코딩
        """
        try:
            # 이미지 로드
            image = Image.open(BytesIO(screenshot_bytes))
            
            # 리사이즈 (비율 유지)
            image.thumbnail((self.screenshot_width, self.screenshot_height), Image.Resampling.LANCZOS)
            
            # PNG로 저장
            buffer = BytesIO()
            image.save(buffer, format='PNG', optimize=True)
            buffer.seek(0)
            
            # Base64 인코딩
            screenshot_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return screenshot_base64
            
        except Exception as e:
            print(f"이미지 리사이즈/인코딩 실패: {e}")
            logger.error(f"이미지 처리 실패: {e}")
            return ""
    
    async def capture_screenshot(self, url: str) -> Optional[str]:
        """
        스크린샷 캡처 (우선순위: Playwright > Selenium)
        """
        # Playwright 시도
        screenshot = await self.capture_screenshot_playwright(url)
        if screenshot:
            return screenshot
        
        # Selenium 대안 시도
        print(f"Playwright 실패, Selenium으로 재시도: {url}")
        screenshot = await self.capture_screenshot_selenium(url)
        if screenshot:
            return screenshot
        
        print(f"모든 스크린샷 캡처 방법 실패: {url}")
        return None
    
    def is_screenshot_needed(self, url: str) -> bool:
        """
        스크린샷 캡처가 필요한지 판단
        """
        # 로컬 URL이나 특정 프로토콜은 제외
        if any(pattern in url.lower() for pattern in [
            'localhost', '127.0.0.1', '192.168.', '10.0.', 'file://', 'ftp://', 'data:'
        ]):
            return False
        
        # HTTP/HTTPS만 허용
        if not url.lower().startswith(('http://', 'https://')):
            return False
        
        return True

# 전역 인스턴스
screenshot_service = ScreenshotService() 