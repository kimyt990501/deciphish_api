from app.core.database import async_session
from app.core.config import settings
from datetime import datetime, timedelta
import logging
import secrets
import string
from sqlalchemy import text
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class APIKeyService:
    """API 키 관리 서비스"""
    
    def __init__(self):
        self.default_expiry_days = 180
        self.default_rate_limit = 1000
    
    def _generate_api_key(self) -> str:
        """안전한 API 키 생성"""
        # API 키 포맷: ak_[32자리 랜덤 문자열]
        alphabet = string.ascii_letters + string.digits
        random_part = ''.join(secrets.choice(alphabet) for _ in range(32))
        return f"ak_{random_part}"
    
    async def create_api_key(self, user_id: int, key_name: str, 
                           permissions: Optional[Dict] = None, 
                           rate_limit_per_hour: int = None,
                           expires_in_days: int = None) -> Optional[Dict]:
        """
        새 API 키 생성
        
        Args:
            user_id: 사용자 ID
            key_name: API 키 이름
            permissions: 권한 설정 (JSON)
            rate_limit_per_hour: 시간당 요청 제한
            expires_in_days: 만료 일수 (기본 180일)
            
        Returns:
            생성된 API 키 정보 또는 None
        """
        try:
            async with async_session() as session:
                # 기본값 설정
                if rate_limit_per_hour is None:
                    rate_limit_per_hour = self.default_rate_limit
                if expires_in_days is None:
                    expires_in_days = self.default_expiry_days
                if permissions is None:
                    permissions = {"phishing_detection": True, "history_access": True}
                
                # API 키 생성
                api_key = self._generate_api_key()
                expires_at = datetime.now() + timedelta(days=expires_in_days)
                
                # 사용자 이름 중복 체크
                check_query = text("""
                SELECT COUNT(*) FROM api_keys 
                WHERE user_id = :user_id AND key_name = :key_name AND is_active = 1
                """)
                result = await session.execute(check_query, {
                    "user_id": user_id, 
                    "key_name": key_name
                })
                
                if result.fetchone()[0] > 0:
                    logger.warning(f"API 키 이름 중복: 사용자 {user_id}, 키 이름 '{key_name}'")
                    return None
                
                # API 키 저장
                insert_query = text("""
                INSERT INTO api_keys 
                (user_id, key_name, api_key, permissions, rate_limit_per_hour, expires_at)
                VALUES (:user_id, :key_name, :api_key, :permissions, :rate_limit_per_hour, :expires_at)
                """)
                
                import json
                await session.execute(insert_query, {
                    "user_id": user_id,
                    "key_name": key_name,
                    "api_key": api_key,
                    "permissions": json.dumps(permissions),
                    "rate_limit_per_hour": rate_limit_per_hour,
                    "expires_at": expires_at
                })
                await session.commit()
                
                logger.info(f"API 키 생성 성공: 사용자 {user_id}, 키 이름 '{key_name}'")
                
                return {
                    "api_key": api_key,
                    "key_name": key_name,
                    "permissions": permissions,
                    "rate_limit_per_hour": rate_limit_per_hour,
                    "expires_at": expires_at.isoformat(),
                    "is_active": True,
                    "created_at": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"API 키 생성 실패: {e}")
            return None
    
    async def get_user_api_keys(self, user_id: int, include_inactive: bool = False) -> List[Dict]:
        """
        사용자의 API 키 목록 조회
        
        Args:
            user_id: 사용자 ID
            include_inactive: 비활성 키도 포함할지 여부
            
        Returns:
            API 키 목록
        """
        try:
            async with async_session() as session:
                query = """
                SELECT id, key_name, api_key, permissions, rate_limit_per_hour, 
                       is_active, last_used, expires_at, created_at, updated_at
                FROM api_keys 
                WHERE user_id = :user_id
                """
                
                if not include_inactive:
                    query += " AND is_active = 1"
                
                query += " ORDER BY created_at DESC"
                
                result = await session.execute(text(query), {"user_id": user_id})
                rows = result.fetchall()
                
                api_keys = []
                for row in rows:
                    import json
                    permissions = json.loads(row[3]) if row[3] else {}
                    
                    # API 키는 일부만 표시 (보안)
                    masked_key = f"{row[2][:8]}...{row[2][-4:]}" if row[2] else ""
                    
                    api_keys.append({
                        "id": row[0],
                        "key_name": row[1],
                        "api_key_masked": masked_key,
                        "permissions": permissions,
                        "rate_limit_per_hour": row[4],
                        "is_active": bool(row[5]),
                        "last_used": row[6].isoformat() if row[6] else None,
                        "expires_at": row[7].isoformat() if row[7] else None,
                        "created_at": row[8].isoformat() if row[8] else None,
                        "updated_at": row[9].isoformat() if row[9] else None,
                        "is_expired": row[7] < datetime.now() if row[7] else False
                    })
                
                return api_keys
                
        except Exception as e:
            logger.error(f"사용자 API 키 조회 실패: {e}")
            return []
    
    async def get_api_key_info(self, api_key: str) -> Optional[Dict]:
        """
        API 키 정보 조회 및 유효성 검사
        
        Args:
            api_key: API 키
            
        Returns:
            API 키 정보 또는 None (유효하지 않은 경우)
        """
        try:
            async with async_session() as session:
                query = text("""
                SELECT ak.id, ak.user_id, ak.key_name, ak.permissions, ak.rate_limit_per_hour, 
                       ak.is_active, ak.expires_at, u.username, u.role, u.is_active as user_active
                FROM api_keys ak
                JOIN users u ON ak.user_id = u.id
                WHERE ak.api_key = :api_key
                """)
                
                result = await session.execute(query, {"api_key": api_key})
                row = result.fetchone()
                
                if not row:
                    return None
                
                # 유효성 검사
                is_key_active = bool(row[5])
                is_user_active = bool(row[9])
                expires_at = row[6]
                is_expired = expires_at < datetime.now() if expires_at else False
                
                if not is_key_active or not is_user_active or is_expired:
                    return None
                
                # 마지막 사용 시간 업데이트
                update_query = text("UPDATE api_keys SET last_used = CURRENT_TIMESTAMP WHERE api_key = :api_key")
                await session.execute(update_query, {"api_key": api_key})
                await session.commit()
                
                import json
                permissions = json.loads(row[3]) if row[3] else {}
                
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "key_name": row[2],
                    "permissions": permissions,
                    "rate_limit_per_hour": row[4],
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "username": row[7],
                    "user_role": row[8]
                }
                
        except Exception as e:
            logger.error(f"API 키 정보 조회 실패: {e}")
            return None
    
    async def deactivate_api_key(self, user_id: int, key_id: int) -> bool:
        """
        API 키 비활성화
        
        Args:
            user_id: 사용자 ID (권한 확인용)
            key_id: API 키 ID
            
        Returns:
            성공 여부
        """
        try:
            async with async_session() as session:
                query = text("""
                UPDATE api_keys 
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = :key_id AND user_id = :user_id
                """)
                
                result = await session.execute(query, {
                    "key_id": key_id,
                    "user_id": user_id
                })
                await session.commit()
                
                if result.rowcount > 0:
                    logger.info(f"API 키 비활성화 성공: 사용자 {user_id}, 키 ID {key_id}")
                    return True
                else:
                    logger.warning(f"API 키 비활성화 실패: 사용자 {user_id}, 키 ID {key_id} (키를 찾을 수 없음)")
                    return False
                    
        except Exception as e:
            logger.error(f"API 키 비활성화 실패: {e}")
            return False
    
    async def update_api_key(self, user_id: int, key_id: int, 
                           key_name: str = None, 
                           rate_limit_per_hour: int = None,
                           permissions: Dict = None) -> bool:
        """
        API 키 정보 업데이트
        
        Args:
            user_id: 사용자 ID (권한 확인용)
            key_id: API 키 ID
            key_name: 새로운 키 이름
            rate_limit_per_hour: 새로운 요청 제한
            permissions: 새로운 권한 설정
            
        Returns:
            성공 여부
        """
        try:
            async with async_session() as session:
                update_fields = []
                params = {"key_id": key_id, "user_id": user_id}
                
                if key_name is not None:
                    update_fields.append("key_name = :key_name")
                    params["key_name"] = key_name
                
                if rate_limit_per_hour is not None:
                    update_fields.append("rate_limit_per_hour = :rate_limit_per_hour")
                    params["rate_limit_per_hour"] = rate_limit_per_hour
                
                if permissions is not None:
                    update_fields.append("permissions = :permissions")
                    import json
                    params["permissions"] = json.dumps(permissions)
                
                if not update_fields:
                    return True  # 업데이트할 것이 없음
                
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                
                query = text(f"""
                UPDATE api_keys 
                SET {', '.join(update_fields)}
                WHERE id = :key_id AND user_id = :user_id
                """)
                
                result = await session.execute(query, params)
                await session.commit()
                
                if result.rowcount > 0:
                    logger.info(f"API 키 업데이트 성공: 사용자 {user_id}, 키 ID {key_id}")
                    return True
                else:
                    logger.warning(f"API 키 업데이트 실패: 사용자 {user_id}, 키 ID {key_id} (키를 찾을 수 없음)")
                    return False
                    
        except Exception as e:
            logger.error(f"API 키 업데이트 실패: {e}")
            return False

# 서비스 인스턴스 생성
api_key_service = APIKeyService() 