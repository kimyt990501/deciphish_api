from app.core.brand_loader import brand_loader
from app.core.utils import extract_domain
import tldextract
import asyncio

async def extract_root_domain(url: str) -> str:
    # tldextract를 사용해 루트 도메인 추출 (예: doc.google.com -> google.com)
    netloc = extract_domain(url)
    ext = tldextract.extract(netloc)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return netloc

async def check_whitelist(url: str) -> dict:
    """
    url의 루트 도메인이 브랜드 도메인과 일치하면
    {'brand': 브랜드명, 'domain': 도메인} 반환, 없으면 None 반환
    """
    root_domain = await extract_root_domain(url)
    brand_list = await brand_loader.get_brand_list()
    for brand in brand_list:
        if brand.get('domain') and brand['domain'].lower() == root_domain:
            return {'brand': brand['name'], 'domain': brand['domain']}
    return None 