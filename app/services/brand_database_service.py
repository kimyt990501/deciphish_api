"""
Brand Database Service for handling brand data operations
"""
import json
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import async_session
from app.services.search_service import SearchService
from app.core.logger import logger


class BrandDatabaseService:
    """Service for brand database operations"""
    
    def __init__(self):
        self.search_service = SearchService()
    
    async def save_brand_info(self, brand_name: str) -> bool:
        """
        새로운 브랜드 정보를 tb_brand_info 테이블에 저장
        브랜드 이름으로 공식 도메인을 찾아서 저장
        
        Args:
            brand_name (str): 브랜드 이름
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # 브랜드 이름으로 공식 도메인 찾기 (시간 제한)
            official_domain = self.search_service.find_best_domain(brand_name)
            
            async with async_session() as session:
                # 중복 확인 (브랜드명으로만)
                check_query = text("""
                SELECT brand_id FROM tb_brand_info 
                WHERE brand_name = :brand_name
                """)
                check_params = {"brand_name": brand_name}
                
                # 도메인이 있으면 도메인 중복도 확인
                if official_domain:
                    check_query = text("""
                    SELECT brand_id FROM tb_brand_info 
                    WHERE brand_name = :brand_name OR official_domain = :official_domain
                    """)
                    check_params["official_domain"] = official_domain
                
                result = await session.execute(check_query, check_params)
                existing = result.fetchone()
                
                if existing:
                    logger.info(f"Brand already exists: {brand_name}")
                    return True
                
                # 새 브랜드 정보 삽입
                insert_query = text("""
                INSERT INTO tb_brand_info (brand_name, official_domain, brand_alias) 
                VALUES (:brand_name, :official_domain, :brand_alias)
                """)
                # 기본 별칭은 빈 배열로 설정
                brand_alias = json.dumps([])
                
                await session.execute(insert_query, {
                    "brand_name": brand_name,
                    "official_domain": official_domain or "",  # 도메인이 없으면 빈 문자열
                    "brand_alias": brand_alias
                })
                await session.commit()
                
                if official_domain:
                    logger.info(f"New brand saved: {brand_name} ({official_domain})")
                else:
                    logger.info(f"New brand saved without domain: {brand_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save brand info: {e}")
            return False
    
    async def get_brand_info(self, brand_name: str) -> Optional[Dict[str, Any]]:
        """
        브랜드 정보 조회
        
        Args:
            brand_name (str): 브랜드 이름
            
        Returns:
            Optional[Dict[str, Any]]: 브랜드 정보 또는 None
        """
        try:
            async with async_session() as session:
                query = text("""
                SELECT * FROM tb_brand_info 
                WHERE brand_name = :brand_name
                """)
                result = await session.execute(query, {"brand_name": brand_name})
                row = result.fetchone()
                
                if row:
                    return dict(row._mapping)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get brand info: {e}")
            return None


# 전역 인스턴스
brand_database_service = BrandDatabaseService() 