import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# 로그 디렉토리 생성
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 로거 설정
logger = logging.getLogger("phishing_detector")
logger.setLevel(logging.DEBUG)

# 기존 핸들러 제거 (중복 방지)
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# TimedRotatingFileHandler 사용 (매일 자정에 로테이션)
log_filename = "phishing_detector.log"
file_handler = TimedRotatingFileHandler(
    log_dir / log_filename,
    when="midnight",
    interval=1,
    backupCount=30,  # 30일치 로그 파일 보관
    encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)

# 로그 파일명을 phishing_detector_YYYYMMDD.log 형태로 변경
file_handler.suffix = "%Y%m%d"
file_handler.namer = lambda name: name.replace(".log", "") + "_" + name.split(".")[-1] + ".log"

# 콘솔 핸들러
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)

# 포맷터
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 핸들러 추가
logger.addHandler(file_handler)
logger.addHandler(console_handler) 