from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router
from app.core.middleware import RequestTimingMiddleware
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os

# 스레드풀 설정 (CPU 코어 수의 2배)
max_workers = min(32, (os.cpu_count() or 1) * 2)
thread_pool = ThreadPoolExecutor(max_workers=max_workers)

app = FastAPI(
    title="Phishing Detector API (New)",
    description="""
    피싱 사이트 탐지를 위한 새로운 API 서비스입니다.
    
    ## 주요 기능
    * URL 기반 피싱 탐지
    * 파비콘 기반 브랜드 인식 (CLIP 모델)
    * 텍스트 기반 브랜드 인식 (Ollama LLM)
    * 신뢰도 분류
    
    ## 사용 방법
    1. URL, HTML, 파비콘을 전송
    2. 피싱 여부와 탐지된 브랜드 정보 반환
    
    ## 동시성 처리
    * 최대 {max_workers}개의 요청을 동시에 처리
    * 블로킹 작업들은 스레드풀에서 실행
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 앱 시작 시 스레드풀을 앱 상태에 저장
@app.on_event("startup")
async def startup_event():
    app.state.thread_pool = thread_pool

# 앱 종료 시 스레드풀 정리
@app.on_event("shutdown")
async def shutdown_event():
    thread_pool.shutdown(wait=True)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영 환경에서는 특정 도메인만 허용하도록 수정
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 미들웨어 추가
app.add_middleware(RequestTimingMiddleware)

app.include_router(router, prefix="/api/v1")