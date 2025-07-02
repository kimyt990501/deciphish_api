from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.auth_service import auth_service
from app.services.api_key_service import api_key_service
from app.core.logger import logger
from typing import Optional, List
import jwt

# JWT Bearer 토큰 설정
security = HTTPBearer(auto_error=False)

async def get_current_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    """JWT 토큰에서 현재 사용자 정보 추출"""
    if not credentials:
        logger.debug("JWT credentials 없음")
        return None
    
    logger.debug(f"JWT 토큰 검증 시도: {credentials.credentials[:20]}...")
    
    try:
        user_data = await auth_service.verify_token_and_get_user(credentials.credentials)
        if user_data:
            logger.debug(f"JWT 토큰 검증 성공: 사용자 {user_data.get('username')} (ID: {user_data.get('id')})")
        else:
            logger.debug("JWT 토큰 검증 실패: 유효하지 않은 토큰 또는 사용자")
        return user_data
    except Exception as e:
        logger.error(f"JWT 토큰 검증 중 예외 발생: {e}")
        return None

async def get_current_user_from_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Header(None, alias="api-key")
) -> Optional[dict]:
    """API 키에서 현재 사용자 정보 추출"""
    # 여러 헤더 이름 지원
    key = x_api_key or api_key
    
    if not key:
        # Query parameter로도 확인
        key = request.query_params.get("api_key")
    
    if not key:
        return None
    
    try:
        api_key_info = await api_key_service.get_api_key_info(key)
        if not api_key_info:
            return None
        
        # 사용자 정보 구성 (JWT 토큰과 동일한 형태로)
        return {
            "id": api_key_info["user_id"],
            "username": api_key_info["username"],
            "role": api_key_info["user_role"],
            "api_key_id": api_key_info["id"],
            "api_key_name": api_key_info["key_name"],
            "api_key_permissions": api_key_info["permissions"],
            "rate_limit_per_hour": api_key_info["rate_limit_per_hour"],
            "auth_method": "api_key"
        }
    except Exception as e:
        logger.debug(f"API 키 검증 실패: {e}")
        return None

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Header(None, alias="api-key")
) -> Optional[dict]:
    """JWT 토큰 또는 API 키에서 현재 사용자 정보 추출 (우선순위: JWT > API Key)"""
    
    logger.debug(f"인증 시도 - URL: {request.url.path}")
    logger.debug(f"Authorization 헤더 존재: {bool(credentials)}")
    logger.debug(f"X-API-Key 헤더: {bool(x_api_key)}")
    logger.debug(f"api-key 헤더: {bool(api_key)}")
    
    # 1. JWT 토큰 우선 확인
    user_from_token = await get_current_user_from_token(credentials)
    if user_from_token:
        user_from_token["auth_method"] = "jwt"
        logger.debug(f"JWT 인증 성공: {user_from_token.get('username')}")
        return user_from_token
    else:
        logger.debug("JWT 인증 실패 또는 토큰 없음")
    
    # 2. API 키 확인
    user_from_api_key = await get_current_user_from_api_key(request, x_api_key, api_key)
    if user_from_api_key:
        logger.debug(f"API 키 인증 성공: {user_from_api_key.get('username')}")
        return user_from_api_key
    else:
        logger.debug("API 키 인증 실패 또는 키 없음")
    
    logger.debug("모든 인증 방법 실패")
    return None

async def get_current_active_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Header(None, alias="api-key")
) -> dict:
    """활성 사용자만 반환 (로그인 필수)"""
    user = await get_current_user(request, credentials, x_api_key, api_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다. JWT 토큰 또는 API 키를 제공해주세요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Header(None, alias="api-key")
) -> Optional[dict]:
    """선택적 사용자 인증 (로그인하지 않아도 됨)"""
    return await get_current_user(request, credentials, x_api_key, api_key)

def require_admin():
    """관리자 권한 필요"""
    async def admin_required(current_user: dict = Depends(get_current_active_user)) -> dict:
        if current_user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="관리자 권한이 필요합니다"
            )
        return current_user
    return Depends(admin_required)

def require_user():
    """일반 사용자 이상 권한 필요"""
    async def user_required(current_user: dict = Depends(get_current_active_user)) -> dict:
        user_role = current_user.get("role")
        if user_role not in ["user", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="사용자 권한이 필요합니다"
            )
        return current_user
    return Depends(user_required)

def require_permission(permission: str):
    """특정 권한 필요 (API 키 사용자용)"""
    async def permission_required(current_user: dict = Depends(get_current_active_user)) -> dict:
        # JWT 토큰 사용자는 기본적으로 모든 권한 허용
        if current_user.get("auth_method") == "jwt":
            return current_user
        
        # API 키 사용자는 권한 확인
        if current_user.get("auth_method") == "api_key":
            permissions = current_user.get("api_key_permissions", {})
            if not permissions.get(permission, False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"'{permission}' 권한이 필요합니다"
                )
        
        return current_user
    return Depends(permission_required)

# 호환성을 위한 기존 함수들
def get_current_user_dep():
    """현재 사용자 가져오기 (Depends 래퍼)"""
    return Depends(get_optional_user)

def get_current_active_user_dep():
    """현재 활성 사용자 가져오기 (Depends 래퍼)"""
    return Depends(get_current_active_user)

def get_optional_user_dep():
    """선택적 사용자 인증 (Depends 래퍼)"""
    return Depends(get_optional_user) 