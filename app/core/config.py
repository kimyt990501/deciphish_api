from pydantic_settings import BaseSettings
import secrets
import os

class Settings(BaseSettings):
    MYSQL_HOST: str
    MYSQL_PORT: int
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DB: str
    HUGGINGFACE_API_KEY: str
    
    # MySQL 연결 풀 설정
    MYSQL_POOL_SIZE: int = 5
    MYSQL_POOL_TIMEOUT: int = 30
    MYSQL_POOL_RECYCLE: int = 3600
    MYSQL_MAX_OVERFLOW: int = 10
    MYSQL_ECHO: bool = False
    
    # Gemini API 키
    GEMINI_API_KEY: str
    
    # JWT 인증 설정
    JWT_SECRET_KEY: str = "phishing-detector-jwt-secret-key-for-development-only-change-in-production"  # 개발용 고정키
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # 비밀번호 정책
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_SPECIAL: bool = False
    PASSWORD_REQUIRE_NUMBERS: bool = False
    PASSWORD_REQUIRE_UPPERCASE: bool = False
    
    # 사용자 세션 설정
    SESSION_CLEANUP_INTERVAL_HOURS: int = 24
    MAX_SESSIONS_PER_USER: int = 5
    
    # 보안 설정
    ALLOWED_HOSTS: list = ["*"]  # 프로덕션에서는 구체적인 도메인 설정
    CORS_ORIGINS: list = ["*"]   # 프로덕션에서는 구체적인 도메인 설정
    
    # 캐시 설정
    CACHE_TTL_HOURS: int = 24
    
    # 환경 설정
    ENVIRONMENT: str = "development"  # development, production
    DEBUG: bool = True

    # 동시성 처리 설정
    CONCURRENT_DETECTION_LIMIT: int = 10
    MAX_WORKERS: int = 4
    REQUEST_TIMEOUT: int = 30
    
    # QR 코드 설정
    QR_LOGO_PATH: str = "static/logo.png"  # QR 코드에 포함할 로고 이미지 경로
    QR_LOGO_ENABLED: bool = True  # 로고 포함 여부 기본값

    class Config:
        env_file = ".env"

settings = Settings() 