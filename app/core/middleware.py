import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from .logger import logger

class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        logger.info(f"Request processed: {request.method} {request.url.path} - {process_time:.3f}s")
        
        return response 