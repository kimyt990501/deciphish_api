import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.logger import logger
from app.core.exceptions import BrandDataError
from typing import Optional, Dict

class BrandService:
    async def check_brand_exists(self, brand_name: str) -> Optional[Dict]:
        """브랜드가 DB에 존재하는지 확인하고 정보 반환"""
        try:
            async for session in get_db():
                result = await session.execute(
                    text("""
                    SELECT brand_name, official_domain, brand_alias 
                    FROM tb_brand_info 
                    WHERE brand_name = :name
                    """),
                    {"name": brand_name}
                )
                brand_info = result.fetchone()

                if brand_info:
                    return {
                        "name": brand_info.brand_name,
                        "domain": brand_info.official_domain,
                        "aliases": json.loads(brand_info.brand_alias) if brand_info.brand_alias else []
                    }
                return None

        except Exception as e:
            logger.error(f"Error checking brand existence: {str(e)}")
            return None

    async def add_new_brand(self, brand_name: str, domain: str, aliases: list = None) -> bool:
        """새로운 브랜드 추가"""
        try:
            async for session in get_db():
                # 브랜드가 이미 존재하는지 확인
                result = await session.execute(
                    text("SELECT brand_name FROM tb_brand_info WHERE brand_name = :name OR official_domain = :domain"),
                    {"name": brand_name, "domain": domain}
                )
                existing_brand = result.fetchone()

                if existing_brand:
                    logger.info(f"Brand already exists: {brand_name}")
                    return False

                # 새로운 브랜드 추가
                aliases_json = json.dumps(aliases if aliases else [])
                await session.execute(
                    text("""
                    INSERT INTO tb_brand_info 
                    (brand_name, official_domain, brand_alias) 
                    VALUES (:name, :domain, :alias)
                    """),
                    {"name": brand_name, "domain": domain, "alias": aliases_json}
                )
                await session.commit()

                logger.info(f"New brand added: {brand_name}")
                return True

        except Exception as e:
            logger.error(f"Error adding new brand: {str(e)}")
            raise BrandDataError(f"Failed to add new brand: {str(e)}")

    async def update_brand_aliases(self, brand_name: str, new_aliases: list) -> bool:
        """브랜드 별칭 업데이트"""
        try:
            async for session in get_db():
                # 현재 별칭 가져오기
                result = await session.execute(
                    text("SELECT brand_alias FROM tb_brand_info WHERE brand_name = :name"),
                    {"name": brand_name}
                )
                current = result.fetchone()

                if not current:
                    logger.warning(f"Brand not found: {brand_name}")
                    return False

                # 기존 별칭과 새로운 별칭 병합
                current_aliases = json.loads(current.brand_alias) if current.brand_alias else []
                updated_aliases = list(set(current_aliases + new_aliases))

                # 별칭 업데이트
                await session.execute(
                    text("UPDATE tb_brand_info SET brand_alias = :alias WHERE brand_name = :name"),
                    {"alias": json.dumps(updated_aliases), "name": brand_name}
                )
                await session.commit()

                logger.info(f"Brand aliases updated: {brand_name}")
                return True

        except Exception as e:
            logger.error(f"Error updating brand aliases: {str(e)}")
            raise BrandDataError(f"Failed to update brand aliases: {str(e)}")

# 싱글톤 인스턴스
brand_service = BrandService() 