#!/bin/bash

fuser -k 8300/tcp

# 작업 디렉토리로 이동
cd /mnt/c/Users/pnet/Desktop/phishing_detector_api_new

# conda 환경 활성화
source /home/kimyt990501/miniconda3/etc/profile.d/conda.sh
conda activate /home/kimyt990501/miniconda3/envs/phishing-detector

# logs 디렉토리 생성
mkdir -p logs

# 필요한 패키지 설치
# echo "Installing required packages..."
# pip install -r requirements.txt

# 서버 실행 (백그라운드) - 동시성 최적화
echo "Starting Phishing Detector API (New) server in background with optimized settings..."

# CPU 코어 수 계산 (최소 1, 최대 4)
WORKERS=$(python3 -c "import os; print(min(4, max(1, os.cpu_count() or 1)))")
echo "Using $WORKERS workers"

nohup uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8300 \
    --workers $WORKERS \
    --worker-class uvicorn.workers.UvicornWorker \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout-keep-alive 10 \
    --limit-concurrency 200 \
    --limit-max-requests 1000 \
    --log-level info > logs/server.log 2>&1 &

# 프로세스 ID 저장
echo $! > logs/server.pid
echo "Server started with PID: $(cat logs/server.pid)" 