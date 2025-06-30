from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from .config import settings
from .logger import logger

# 비동기 엔진 생성
engine = create_async_engine(
    f"mysql+aiomysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DB}",
    poolclass=AsyncAdaptedQueuePool,
    pool_size=settings.MYSQL_POOL_SIZE,
    max_overflow=settings.MYSQL_MAX_OVERFLOW,
    pool_timeout=settings.MYSQL_POOL_TIMEOUT,
    pool_recycle=settings.MYSQL_POOL_RECYCLE,
    echo=settings.MYSQL_ECHO,
    pool_pre_ping=True  # 연결 상태 확인
)

# 비동기 세션 생성
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def get_db():
    """데이터베이스 세션 제공"""
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close() 