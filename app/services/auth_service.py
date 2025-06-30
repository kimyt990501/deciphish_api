from app.core.database import async_session
from datetime import datetime, timedelta
import logging
import hashlib
import secrets
import jwt
from passlib.context import CryptContext
from sqlalchemy import text
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 비밀번호 해싱 설정
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__rounds=12
)

# JWT 설정 (환경변수에서 가져오기)
from app.core.config import settings

SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS

class User(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    last_login: Optional[datetime]
    created_at: datetime

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "user"

class UserLogin(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User

class AuthService:
    """사용자 인증 서비스"""
    
    def __init__(self):
        self.pwd_context = pwd_context
    
    def hash_password(self, password: str) -> str:
        """비밀번호 해싱"""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """비밀번호 검증"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """액세스 토큰 생성"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def create_refresh_token(self, data: dict) -> str:
        """리프레시 토큰 생성"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[dict]:
        """토큰 검증"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") != token_type:
                return None
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.JWTError:
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """사용자명으로 사용자 조회"""
        try:
            async with async_session() as session:
                query = text("""
                SELECT id, username, email, password_hash, full_name, role, is_active, last_login, created_at
                FROM users 
                WHERE username = :username AND is_active = 1
                """)
                
                result = await session.execute(query, {"username": username})
                row = result.fetchone()
                
                if row:
                    return {
                        "id": row[0],
                        "username": row[1],
                        "email": row[2],
                        "password_hash": row[3],
                        "full_name": row[4],
                        "role": row[5],
                        "is_active": bool(row[6]),
                        "last_login": row[7],
                        "created_at": row[8]
                    }
                return None
                
        except Exception as e:
            logger.error(f"사용자 조회 실패: {e}")
            return None
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """사용자 ID로 사용자 조회"""
        try:
            async with async_session() as session:
                query = text("""
                SELECT id, username, email, full_name, role, is_active, last_login, created_at
                FROM users 
                WHERE id = :user_id AND is_active = 1
                """)
                
                result = await session.execute(query, {"user_id": user_id})
                row = result.fetchone()
                
                if row:
                    return {
                        "id": row[0],
                        "username": row[1],
                        "email": row[2],
                        "full_name": row[3],
                        "role": row[4],
                        "is_active": bool(row[5]),
                        "last_login": row[6],
                        "created_at": row[7]
                    }
                return None
                
        except Exception as e:
            logger.error(f"사용자 조회 실패: {e}")
            return None
    
    async def create_user(self, user_data: UserCreate) -> Optional[Dict[str, Any]]:
        """새 사용자 생성"""
        try:
            async with async_session() as session:
                # 중복 확인
                check_query = text("""
                SELECT COUNT(*) FROM users 
                WHERE username = :username OR email = :email
                """)
                
                result = await session.execute(check_query, {
                    "username": user_data.username,
                    "email": user_data.email
                })
                
                if result.fetchone()[0] > 0:
                    return None  # 이미 존재하는 사용자
                
                # 비밀번호 해싱
                hashed_password = self.hash_password(user_data.password)
                
                # 사용자 생성
                insert_query = text("""
                INSERT INTO users (username, email, password_hash, full_name, role)
                VALUES (:username, :email, :password_hash, :full_name, :role)
                """)
                
                await session.execute(insert_query, {
                    "username": user_data.username,
                    "email": user_data.email,
                    "password_hash": hashed_password,
                    "full_name": user_data.full_name,
                    "role": user_data.role
                })
                
                await session.commit()
                
                # 생성된 사용자 정보 반환
                return await self.get_user_by_username(user_data.username)
                
        except Exception as e:
            logger.error(f"사용자 생성 실패: {e}")
            return None
    
    async def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """사용자 인증"""
        user = await self.get_user_by_username(username)
        if not user:
            return None
        
        if not self.verify_password(password, user["password_hash"]):
            return None
        
        # 마지막 로그인 시간 업데이트
        await self.update_last_login(user["id"])
        
        # password_hash 제거 후 반환
        user.pop("password_hash", None)
        return user
    
    async def update_last_login(self, user_id: int):
        """마지막 로그인 시간 업데이트"""
        try:
            async with async_session() as session:
                query = text("""
                UPDATE users 
                SET last_login = :last_login 
                WHERE id = :user_id
                """)
                
                await session.execute(query, {
                    "user_id": user_id,
                    "last_login": datetime.utcnow()
                })
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"마지막 로그인 시간 업데이트 실패: {e}")
    
    async def create_session(self, user_id: int, token_hash: str, ip_address: str, user_agent: str) -> bool:
        """세션 생성"""
        try:
            async with async_session() as session:
                query = text("""
                INSERT INTO user_sessions (user_id, token_hash, expires_at, ip_address, user_agent)
                VALUES (:user_id, :token_hash, :expires_at, :ip_address, :user_agent)
                """)
                
                expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
                
                await session.execute(query, {
                    "user_id": user_id,
                    "token_hash": hashlib.sha256(token_hash.encode()).hexdigest(),
                    "expires_at": expires_at,
                    "ip_address": ip_address,
                    "user_agent": user_agent
                })
                
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"세션 생성 실패: {e}")
            return False
    
    async def revoke_session(self, token_hash: str) -> bool:
        """세션 무효화"""
        try:
            async with async_session() as session:
                query = text("""
                UPDATE user_sessions 
                SET is_active = 0 
                WHERE token_hash = :token_hash
                """)
                
                await session.execute(query, {
                    "token_hash": hashlib.sha256(token_hash.encode()).hexdigest()
                })
                
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"세션 무효화 실패: {e}")
            return False
    
    async def login(self, username: str, password: str, ip_address: str, user_agent: str) -> Optional[TokenResponse]:
        """로그인"""
        # 사용자 인증
        user = await self.authenticate_user(username, password)
        if not user:
            return None
        
        # 토큰 생성
        token_data = {"sub": str(user["id"]), "username": user["username"]}
        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)
        
        # 세션 생성
        await self.create_session(user["id"], refresh_token, ip_address, user_agent)
        
        # User 객체 생성
        user_obj = User(**user)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_obj
        )
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """액세스 토큰 갱신"""
        payload = self.verify_token(refresh_token, "refresh")
        if not payload:
            return None
        
        user_id = int(payload.get("sub"))
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        # 새 액세스 토큰 생성
        token_data = {"sub": str(user["id"]), "username": user["username"]}
        new_access_token = self.create_access_token(token_data)
        
        return new_access_token
    
    async def change_password(self, user_id: int, current_password: str, new_password: str) -> bool:
        """비밀번호 변경"""
        try:
            async with async_session() as session:
                # 현재 사용자 정보 조회 (비밀번호 해시 포함)
                query = text("""
                SELECT password_hash FROM users 
                WHERE id = :user_id AND is_active = 1
                """)
                
                result = await session.execute(query, {"user_id": user_id})
                row = result.fetchone()
                
                if not row:
                    logger.error(f"사용자를 찾을 수 없음: {user_id}")
                    return False
                
                # 현재 비밀번호 확인
                if not self.verify_password(current_password, row[0]):
                    logger.error(f"현재 비밀번호가 일치하지 않음: {user_id}")
                    return False
                
                # 새 비밀번호 해싱
                new_password_hash = self.hash_password(new_password)
                
                # 비밀번호 업데이트
                update_query = text("""
                UPDATE users 
                SET password_hash = :password_hash, updated_at = :updated_at
                WHERE id = :user_id
                """)
                
                await session.execute(update_query, {
                    "user_id": user_id,
                    "password_hash": new_password_hash,
                    "updated_at": datetime.utcnow()
                })
                
                await session.commit()
                logger.info(f"비밀번호 변경 성공: {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"비밀번호 변경 실패: {e}")
            return False
    
    async def update_user_info(self, user_id: int, user_data: UserUpdate) -> Optional[Dict[str, Any]]:
        """사용자 개인정보 수정"""
        try:
            async with async_session() as session:
                # 업데이트할 필드들 준비
                update_fields = []
                update_values = {"user_id": user_id, "updated_at": datetime.utcnow()}
                
                if user_data.full_name is not None:
                    update_fields.append("full_name = :full_name")
                    update_values["full_name"] = user_data.full_name
                
                if user_data.email is not None:
                    # 이메일 중복 체크
                    check_query = text("""
                    SELECT COUNT(*) FROM users 
                    WHERE email = :email AND id != :user_id
                    """)
                    
                    result = await session.execute(check_query, {
                        "email": user_data.email,
                        "user_id": user_id
                    })
                    
                    if result.fetchone()[0] > 0:
                        logger.error(f"이메일이 이미 사용 중: {user_data.email}")
                        return None
                    
                    update_fields.append("email = :email")
                    update_values["email"] = user_data.email
                
                if not update_fields:
                    # 업데이트할 내용이 없음
                    return await self.get_user_by_id(user_id)
                
                # 업데이트 실행
                update_fields.append("updated_at = :updated_at")
                update_query = text(f"""
                UPDATE users 
                SET {', '.join(update_fields)}
                WHERE id = :user_id
                """)
                
                await session.execute(update_query, update_values)
                await session.commit()
                
                logger.info(f"사용자 정보 수정 성공: {user_id}")
                
                # 수정된 사용자 정보 반환
                return await self.get_user_by_id(user_id)
                
        except Exception as e:
            logger.error(f"사용자 정보 수정 실패: {e}")
            return None
    
    async def deactivate_user(self, user_id: int) -> bool:
        """사용자 계정 비활성화"""
        try:
            async with async_session() as session:
                query = text("""
                UPDATE users 
                SET is_active = 0, updated_at = :updated_at
                WHERE id = :user_id
                """)
                
                await session.execute(query, {
                    "user_id": user_id,
                    "updated_at": datetime.utcnow()
                })
                
                await session.commit()
                logger.info(f"사용자 계정 비활성화 성공: {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"사용자 계정 비활성화 실패: {e}")
            return False

# 전역 인증 서비스 인스턴스
auth_service = AuthService() 