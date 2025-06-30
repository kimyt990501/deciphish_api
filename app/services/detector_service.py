from app.pipeline.phishing_pipeline import phishing_detector_base64
from app.core.brand_loader import brand_loader
from app.services.web_content_collector import get_web_collector
from app.core.logger import logger

async def detect_phishing_base64(url, html, favicon_b64):
    brand_list = await brand_loader.get_brand_list()
    result = await phishing_detector_base64(
        url=url,
        html=html,
        favicon_b64=favicon_b64,
        brand_list=brand_list
    )
    return result

async def detect_phishing_from_url(url: str):
    """
    URL만 받아서 내부적으로 HTML과 favicon을 수집하여 피싱 탐지
    
    Args:
        url: 검사할 URL
        
    Returns:
        피싱 탐지 결과
    """
    try:
        logger.info(f"Starting phishing detection for URL: {url}")
        
        # 웹 콘텐츠 수집
        web_collector = get_web_collector()
        html_content, favicon_base64 = web_collector.collect_web_content(url)
        
        if not html_content:
            logger.error(f"Failed to download HTML from {url}")
            return {
                "is_phish": 0,
                "reason": "failed_to_download_html",
                "detected_brand": None,
                "error": "HTML 다운로드 실패"
            }
        
        logger.info(f"Successfully collected web content from {url}")
        logger.info(f"HTML length: {len(html_content)} characters")
        logger.info(f"Favicon collected: {favicon_base64 is not None}")
        
        # 기존 피싱 탐지 로직 실행
        brand_list = await brand_loader.get_brand_list()
        result = await phishing_detector_base64(
            url=url,
            html=html_content,
            favicon_b64=favicon_base64,
            brand_list=brand_list
        )
        
        logger.info(f"Phishing detection completed for {url}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in detect_phishing_from_url for {url}: {e}")
        return {
            "is_phish": 0,
            "reason": "internal_error",
            "detected_brand": None,
            "error": str(e)
        }