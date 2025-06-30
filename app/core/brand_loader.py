import json
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .exceptions import BrandDataError
from .logger import logger
import time

class BrandLoader:
    def __init__(self):
        self._brands_cache = None
        self._last_update_time = None
        self._cache_ttl = 3600  # 1시간 캐시
        self._lock = asyncio.Lock()  # 비동기 락 추가

    async def get_brand_list(self) -> list:
        """브랜드 목록 조회 (캐시 적용)"""
        current_time = time.time()
        
        # 캐시가 있고 TTL이 지나지 않았다면 캐시된 데이터 반환
        if (self._brands_cache is not None and 
            self._last_update_time is not None and 
            (current_time - self._last_update_time) < self._cache_ttl):
            logger.info("Returning cached brand data")
            return self._brands_cache

        # 락을 획득하여 동시성 제어
        async with self._lock:
            # 락을 획득한 후 다시 한번 캐시 체크
            if (self._brands_cache is not None and 
                self._last_update_time is not None and 
                (current_time - self._last_update_time) < self._cache_ttl):
                logger.info("Returning cached brand data (after lock)")
                return self._brands_cache

            try:
                async for session in get_db():
                    result = await session.execute(
                        text("""
                        SELECT brand_name as name, 
                               official_domain as domain, 
                               brand_alias as alias
                        FROM tb_brand_info
                        """)
                    )
                    rows = result.fetchall()
                    
                    # 결과를 딕셔너리 리스트로 변환
                    brands = []
                    for row in rows:
                        brand = {
                            'name': row.name,
                            'domain': row.domain,
                            'alias': []
                        }
                        try:
                            if row.alias:
                                brand['alias'] = json.loads(row.alias)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse alias for brand {brand['name']}: {str(e)}")
                        
                        brands.append(brand)

                    # 캐시 업데이트
                    self._brands_cache = brands
                    self._last_update_time = current_time
                    
                    logger.info(f"Successfully loaded {len(brands)} brands (cached)")
                    return brands

            except Exception as e:
                logger.error(f"Error loading brand data: {str(e)}")
                raise BrandDataError(f"Failed to load brand data: {str(e)}")

    async def clear_cache(self):
        """캐시 초기화"""
        async with self._lock:
            self._brands_cache = None
            self._last_update_time = None
            logger.info("Brand cache cleared")

# 싱글톤 인스턴스
brand_loader = BrandLoader()