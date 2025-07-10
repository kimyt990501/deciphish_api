#!/bin/bash

# CPU 코어 수 계산 (도커 환경)
if [ -n "$MAX_WORKERS" ]; then
    WORKERS=$MAX_WORKERS
else
    # 도커 컨테이너의 CPU 리소스 한계 확인
    if [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ] && [ -r /sys/fs/cgroup/cpu/cpu.cfs_period_us ]; then
        quota=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
        period=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)
        if [ "$quota" -gt 0 ] && [ "$period" -gt 0 ]; then
            WORKERS=$(( (quota + period - 1) / period ))
        else
            WORKERS=$(nproc)
        fi
    else
        WORKERS=$(nproc)
    fi
    
    # 최소 1개, 최대 4개로 제한
    WORKERS=$(( WORKERS < 1 ? 1 : WORKERS ))
    WORKERS=$(( WORKERS > 4 ? 4 : WORKERS ))
fi

echo "Starting Phishing Detector API with optimized settings"
echo "   Workers: $WORKERS"
echo "   Concurrent Detection Limit: ${CONCURRENT_DETECTION_LIMIT:-10}"
echo "   Request Timeout: ${REQUEST_TIMEOUT:-30}"

# uvicorn 서버 실행 (최적화된 설정)
if [ "$WORKERS" -gt 1 ]; then
    # 멀티 워커 환경에서는 gunicorn 사용
    echo "   Using Gunicorn with $WORKERS workers for better performance"
    exec gunicorn app.main:app \
        --bind 0.0.0.0:8300 \
        --workers $WORKERS \
        --worker-class uvicorn.workers.UvicornWorker \
        --max-requests 1000 \
        --max-requests-jitter 100 \
        --timeout 30 \
        --keep-alive 10 \
        --log-level ${LOG_LEVEL:-info} \
        --access-logfile - \
        --error-logfile -
else
    # 단일 워커 환경에서는 uvicorn 사용
    echo "   Using single Uvicorn worker"
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8300 \
        --timeout-keep-alive 10 \
        --limit-concurrency 200 \
        --log-level ${LOG_LEVEL:-info}
fi 