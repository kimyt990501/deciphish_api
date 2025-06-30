from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.auth_service import auth_service
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

# JWT Bearer 토큰 설정
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보 가져오기"""
    token = credentials.credentials
    
    # 토큰 검증
    payload = auth_service.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 사용자 정보 조회
    user_id = int(payload.get("sub"))
    user = await auth_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    """활성 사용자 확인"""
    if not current_user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비활성 사용자입니다"
        )
    return current_user

def require_roles(allowed_roles: List[str]):
    """특정 역할 권한 필요"""
    async def role_checker(current_user: dict = Depends(get_current_active_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="권한이 부족합니다"
            )
        return current_user
    
    return role_checker

async def get_optional_user(request: Request):
    """선택적 사용자 인증 (토큰이 없어도 허용)"""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        
        token = auth_header.split(" ")[1]
        payload = auth_service.verify_token(token)
        
        if not payload:
            return None
        
        user_id = int(payload.get("sub"))
        user = await auth_service.get_user_by_id(user_id)
        
        return user if user and user.get("is_active") else None
        
    except Exception as e:
        logger.warning(f"선택적 인증 실패: {e}")
        return None

# 편의 함수들
def require_admin():
    """관리자 권한 필요"""
    return Depends(require_roles(["admin"]))

def require_user():
    """사용자 권한 필요 (user, admin)"""
    return Depends(require_roles(["user", "admin"]))

def get_current_user_dep():
    """현재 사용자 가져오기 (Depends 래퍼)"""
    return Depends(get_current_user)

def get_current_active_user_dep():
    """현재 활성 사용자 가져오기 (Depends 래퍼)"""
    return Depends(get_current_active_user)

def get_optional_user_dep():
    """선택적 사용자 인증 (Depends 래퍼)"""
    return Depends(get_optional_user)

# 기존 클래스 기반 접근 방식과의 호환성을 위한 래퍼
class AuthMiddleware:
    """인증 미들웨어 - 호환성 유지용"""
    
    async def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(security)):
        return await get_current_user(credentials)
    
    async def get_current_active_user(self, current_user: dict = Depends(get_current_user)):
        return await get_current_active_user(current_user)
    
    def require_roles(self, allowed_roles: List[str]):
        return require_roles(allowed_roles)
    
    async def get_optional_user(self, request: Request):
        return await get_optional_user(request)

# 전역 미들웨어 인스턴스 (호환성 유지)
auth_middleware = AuthMiddleware() 