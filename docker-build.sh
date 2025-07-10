#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 함수 정의
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 도커 이미지 이름
IMAGE_NAME="phishing-detector-api"
TAG="latest"

# 빌드 함수
build_image() {
    print_info "도커 이미지 빌드를 시작합니다... (동시성 최적화 포함)"
    docker build -f Dockerfile.optimized -t ${IMAGE_NAME}:${TAG} .
    
    if [ $? -eq 0 ]; then
        print_info "도커 이미지 빌드가 완료되었습니다!"
    else
        print_error "도커 이미지 빌드에 실패했습니다."
        exit 1
    fi
}

# 캐시 없이 빌드 함수
clean_build_image() {
    print_info "캐시 없이 도커 이미지를 다시 빌드합니다..."
    print_warning "이 과정은 오래 걸릴 수 있습니다..."
    docker build --no-cache -f Dockerfile.optimized -t ${IMAGE_NAME}:${TAG} .
    
    if [ $? -eq 0 ]; then
        print_info "도커 이미지 빌드가 완료되었습니다!"
    else
        print_error "도커 이미지 빌드에 실패했습니다."
        exit 1
    fi
}

# 개발 환경 실행
run_dev() {
    print_info "개발 환경을 시작합니다... (동시성 최적화 적용)"
    docker-compose up --build -d
    if [ $? -eq 0 ]; then
        print_info "개발 서버가 http://localhost:8300 에서 실행 중입니다."
        print_info "API 문서: http://localhost:8300/docs"
        print_info "MySQL: localhost:33306"
        print_info "동시 탐지 제한: 10개 요청"
        print_info "워커 수: 2개 (자동 조정)"
        print_info ""
        print_info "로그 확인: ./docker-build.sh logs"
        print_info "상태 확인: ./docker-build.sh status"
        print_info "중지: ./docker-build.sh stop"
    else
        print_error "개발 환경 시작에 실패했습니다."
        exit 1
    fi
}

# 캐시 없이 개발 환경 실행
clean_run_dev() {
    print_info "캐시 없이 개발 환경을 시작합니다..."
    docker-compose build --no-cache
    docker-compose up -d
    if [ $? -eq 0 ]; then
        print_info "개발 서버가 http://localhost:8300 에서 실행 중입니다."
        print_info "API 문서: http://localhost:8300/docs"
        print_info "MySQL: localhost:33306"
        print_info "동시 탐지 제한: 10개 요청"
        print_info "워커 수: 2개 (자동 조정)"
    else
        print_error "개발 환경 시작에 실패했습니다."
        exit 1
    fi
}

# 운영 환경 실행
run_prod() {
    print_info "운영 환경을 시작합니다... (고성능 동시성 설정)"
    docker-compose -f docker-compose.prod.yml up --build -d
    if [ $? -eq 0 ]; then
        print_info "운영 서버가 http://localhost:8300 에서 실행 중입니다."
        print_info "API 문서: http://localhost:8300/docs"
        print_info "MySQL: localhost:33306"
        print_info "동시 탐지 제한: 20개 요청"
        print_info "워커 수: 4개 (자동 조정)"
        print_info "메모리 제한: 4GB"
        print_info "CPU 제한: 2코어"
    else
        print_error "운영 환경 시작에 실패했습니다."
        exit 1
    fi
}

# 캐시 없이 운영 환경 실행
clean_run_prod() {
    print_info "캐시 없이 운영 환경을 시작합니다..."
    docker-compose -f docker-compose.prod.yml build --no-cache
    docker-compose -f docker-compose.prod.yml up -d
    if [ $? -eq 0 ]; then
        print_info "운영 서버가 http://localhost:8300 에서 실행 중입니다."
        print_info "API 문서: http://localhost:8300/docs"
        print_info "MySQL: localhost:33306"
        print_info "동시 탐지 제한: 20개 요청"
        print_info "워커 수: 4개 (자동 조정)"
    else
        print_error "운영 환경 시작에 실패했습니다."
        exit 1
    fi
}

# phpMyAdmin 포함 실행
run_with_phpmyadmin() {
    print_info "phpMyAdmin과 함께 개발 환경을 시작합니다..."
    docker-compose --profile with-phpmyadmin up --build -d
    if [ $? -eq 0 ]; then
        print_info "개발 서버가 http://localhost:8300 에서 실행 중입니다."
        print_info "phpMyAdmin이 http://localhost:8080 에서 실행 중입니다."
        print_info "MySQL 접속 정보:"
        print_info "  - 호스트: localhost"
        print_info "  - 포트: 33306"
        print_info "  - 사용자: phishing_user"
        print_info "  - 비밀번호: phishing_password"
        print_info "  - 데이터베이스: phishing_detector"
        print_info "동시 탐지 제한: 10개 요청"
    else
        print_error "환경 시작에 실패했습니다."
        exit 1
    fi
}

# 운영 환경 phpMyAdmin 포함 실행
run_prod_with_phpmyadmin() {
    print_info "phpMyAdmin과 함께 운영 환경을 시작합니다..."
    docker-compose -f docker-compose.prod.yml --profile with-phpmyadmin up --build -d
    if [ $? -eq 0 ]; then
        print_info "운영 서버가 http://localhost:8300 에서 실행 중입니다."
        print_info "phpMyAdmin이 http://localhost:8080 에서 실행 중입니다."
        print_info "MySQL 접속 정보:"
        print_info "  - 호스트: localhost"
        print_info "  - 포트: 33306"
        print_info "  - 사용자: phishing_user"
        print_info "  - 비밀번호: phishing_password"
        print_info "  - 데이터베이스: phishing_detector"
        print_info "동시 탐지 제한: 20개 요청"
    else
        print_error "환경 시작에 실패했습니다."
        exit 1
    fi
}

# 서비스 중지
stop_services() {
    print_info "서비스를 중지합니다..."
    docker-compose down
    docker-compose -f docker-compose.prod.yml down
    if [ $? -eq 0 ]; then
        print_info "서비스가 중지되었습니다."
    else
        print_warning "일부 서비스 중지에 문제가 있을 수 있습니다."
    fi
}

# 로그 확인
show_logs() {
    print_info "서비스 로그를 확인합니다..."
    docker-compose logs -f
}

# API 로그만 확인
show_api_logs() {
    print_info "API 서비스 로그를 확인합니다..."
    docker-compose logs -f phishing-detector-api
}

# 컨테이너 상태 확인
show_status() {
    print_info "컨테이너 상태를 확인합니다..."
    echo ""
    docker-compose ps
    echo ""
    print_info "더 자세한 정보는 'docker stats'를 사용하세요."
}

# 도움말
show_help() {
    echo "Phishing Detector API - 동시성 최적화 버전"
    echo "사용법: $0 [옵션]"
    echo ""
    echo "빌드 옵션:"
    echo "  build               - 도커 이미지만 빌드 (캐시 사용)"
    echo "  clean-build         - 도커 이미지만 빌드 (캐시 없이)"
    echo ""
    echo "실행 옵션:"
    echo "  dev                 - 개발 환경 실행 (캐시 사용) 추천"
    echo "  clean-dev           - 개발 환경 실행 (캐시 없이)"
    echo "  prod                - 운영 환경 실행 (캐시 사용)"
    echo "  clean-prod          - 운영 환경 실행 (캐시 없이)"
    echo "  dev-phpmyadmin      - phpMyAdmin 포함 개발 환경 실행"
    echo "  prod-phpmyadmin     - phpMyAdmin 포함 운영 환경 실행"
    echo ""
    echo "🛠️  관리 옵션:"
    echo "  stop                - 서비스 중지"
    echo "  logs                - 전체 로그 확인 자주 사용"
    echo "  api-logs            - API 로그만 확인"
    echo "  status              - 컨테이너 상태 확인"
    echo "  help                - 이 도움말 표시"
    echo ""
    echo "예시:"
    echo "  $0 dev              # 개발 환경 실행"
    echo "  $0 logs             # 로그 확인"
    echo "  $0 status           # 상태 확인"
    echo "  $0 stop             # 중지"
    echo ""
    echo "동시성 최적화 기능:"
    echo "  • 개발환경: 10개 요청 동시 처리, 2개 워커"
    echo "  • 운영환경: 20개 요청 동시 처리, 4개 워커"
    echo "  • 비동기 HTTP 클라이언트 (aiohttp)"
    echo "  • 자동 CPU 기반 워커 수 조정"
    echo ""
    echo "처음 사용 시: $0 clean-dev (권장)"
}

# 메인 로직
case "$1" in
    "build")
        build_image
        ;;
    "clean-build")
        clean_build_image
        ;;
    "dev")
        run_dev
        ;;
    "clean-dev")
        clean_run_dev
        ;;
    "prod")
        run_prod
        ;;
    "clean-prod")
        clean_run_prod
        ;;
    "dev-phpmyadmin")
        run_with_phpmyadmin
        ;;
    "prod-phpmyadmin")
        run_prod_with_phpmyadmin
        ;;
    "stop")
        stop_services
        ;;
    "logs")
        show_logs
        ;;
    "api-logs")
        show_api_logs
        ;;
    "status")
        show_status
        ;;
    "help"|"--help"|"-h"|"")
        show_help
        ;;
    *)
        print_error "알 수 없는 옵션입니다: $1"
        echo ""
        show_help
        exit 1
        ;;
esac 