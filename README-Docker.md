# 피싱 탐지 API - Docker 가이드

이 문서는 피싱 탐지 API 서비스를 Docker로 실행하는 방법을 설명합니다.

## 📋 사전 요구사항

- Docker (20.10 이상)
- Docker Compose (2.0 이상)
- 최소 4GB RAM (ML 모델 로딩을 위해)

## 🚀 빠른 시작

### 1. 개발 환경 실행

```bash
# 스크립트 실행 권한 부여
chmod +x docker-build.sh

# 개발 환경 실행
./docker-build.sh dev
```

### 2. 운영 환경 실행

```bash
# 운영 환경 실행
./docker-build.sh prod
```

### 3. 수동 실행

```bash
# 이미지 빌드
docker build -t phishing-detector-api .

# 개발 환경
docker-compose up -d

# 운영 환경
docker-compose -f docker-compose.prod.yml up -d
```

## 📁 파일 구조

```
phishing_detector_api_new/
├── Dockerfile                 # 도커 이미지 정의
├── .dockerignore             # 도커 빌드 시 제외할 파일들
├── docker-compose.yml        # 개발 환경 설정
├── docker-compose.prod.yml   # 운영 환경 설정
├── docker-build.sh           # 빌드 및 실행 스크립트
├── requirements.txt          # Python 의존성
├── mysql/
│   └── init/
│       ├── 01-init.sql       # 데이터베이스 초기화
│       └── 02-brand-data.sql # 브랜드 데이터 초기화
└── app/                      # 애플리케이션 코드
```

## 🗄️ 데이터베이스 초기화

### 브랜드 데이터 자동 로드

MySQL 컨테이너가 처음 시작될 때 다음 작업이 자동으로 수행됩니다:

1. **데이터베이스 생성**: `phishing_detector` 데이터베이스 생성
2. **테이블 생성**: `tb_brand_info` 테이블 생성
3. **브랜드 데이터 삽입**: `brand_data_with_favicon.json`의 모든 브랜드 정보를 테이블에 삽입

### 브랜드 정보 테이블 구조

```sql
CREATE TABLE tb_brand_info (
    brand_id INT AUTO_INCREMENT COMMENT '브랜드 인덱스' PRIMARY KEY,
    brand_name VARCHAR(255) NOT NULL COMMENT '브랜드 이름',
    official_domain VARCHAR(255) NOT NULL COMMENT '브랜드의 공식 도메인',
    brand_alias JSON NULL COMMENT '브랜드 별칭',
    insert_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL COMMENT '데이터 삽입 일자',
    upate_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '데이터 수정 일자'
) COMMENT '브랜드 관련 정보 테이블 (피싱 탐지 용)';
```

### 데이터 확인

phpMyAdmin을 통해 브랜드 데이터를 확인할 수 있습니다:

```bash
# phpMyAdmin 포함하여 실행
./docker-build.sh dev with-phpmyadmin

# 브라우저에서 접속: http://localhost:8080
# 데이터베이스: phishing_detector
# 테이블: tb_brand_info
```

## 🔧 스크립트 사용법

### docker-build.sh 옵션

```bash
./docker-build.sh [옵션]

옵션:
  build     - 도커 이미지만 빌드
  dev       - 개발 환경 실행
  prod      - 운영 환경 실행
  stop      - 서비스 중지
  logs      - 로그 확인
  status    - 컨테이너 상태 확인
  help      - 도움말 표시
```

### 예시

```bash
# 개발 환경 시작
./docker-build.sh dev

# 로그 확인
./docker-build.sh logs

# 서비스 중지
./docker-build.sh stop
```

## 🌐 서비스 접근

- **API 서버**: http://localhost:8300
- **API 문서**: http://localhost:8300/docs
- **ReDoc 문서**: http://localhost:8300/redoc
- **MySQL 데이터베이스**: localhost:33306
- **phpMyAdmin**: http://localhost:8080 (with-phpmyadmin 프로필 사용 시)

## 📊 헬스체크

서비스는 자동으로 헬스체크를 수행합니다:

```bash
# 헬스체크 엔드포인트
curl http://localhost:8300/api/v1/health
```

## 🔍 로그 확인

```bash
# 실시간 로그 확인
docker-compose logs -f

# 특정 서비스 로그만 확인
docker-compose logs -f phishing-detector-api
```

## 🛠️ 개발 환경 vs 운영 환경

### 개발 환경 (docker-compose.yml)
- 코드 변경 시 자동 반영 (볼륨 마운트)
- 디버그 로그 활성화
- 포트: 8300

### 운영 환경 (docker-compose.prod.yml)
- 리소스 제한 설정
- 프로덕션 로그 레벨
- Nginx 리버스 프록시 (선택사항)
- 자동 재시작 정책

## 🔧 환경 변수

### 환경 변수 설정

보안을 위해 MySQL 비밀번호는 환경 변수로 관리하는 것을 권장합니다.

1. **환경 변수 파일 생성**:
```bash
# .env 파일 생성
cat > .env << EOF
# MySQL 데이터베이스 설정
MYSQL_ROOT_PASSWORD=your_secure_root_password_here
MYSQL_DATABASE=phishing_detector
MYSQL_USER=phishing_user
MYSQL_PASSWORD=your_secure_password_here

# API 서버 설정
API_HOST=0.0.0.0
API_PORT=8300
LOG_LEVEL=info

# 개발 환경 설정
DEV_LOG_LEVEL=debug
EOF
```

2. **환경 변수 직접 설정**:
```bash
# Linux/Mac
export MYSQL_ROOT_PASSWORD=your_secure_root_password
export MYSQL_PASSWORD=your_secure_password

# Windows PowerShell
$env:MYSQL_ROOT_PASSWORD="your_secure_root_password"
$env:MYSQL_PASSWORD="your_secure_password"
```

### 기본 환경 변수
- `PYTHONPATH=/app`: Python 경로 설정
- `PYTHONUNBUFFERED=1`: Python 출력 버퍼링 비활성화
- `LOG_LEVEL=info`: 로그 레벨 설정

### MySQL 환경 변수
- `MYSQL_ROOT_PASSWORD`: MySQL root 비밀번호 (기본값: rootpassword)
- `MYSQL_DATABASE`: 데이터베이스 이름 (기본값: phishing_detector)
- `MYSQL_USER`: MySQL 사용자 이름 (기본값: phishing_user)
- `MYSQL_PASSWORD`: MySQL 사용자 비밀번호 (기본값: phishing_password)

### 데이터베이스 설정 (필요시)
```yaml
environment:
  - DATABASE_URL=mysql+pymysql://user:password@host:port/database
```

## 📦 볼륨 마운트

### 로그 디렉토리
```yaml
volumes:
  - ./logs:/app/logs
```

### 모델 파일 (선택사항)
```yaml
volumes:
  - ./app/services/crp_classifier/models:/app/app/services/crp_classifier/models:ro
  - ./app/services/favicon_service/data:/app/app/services/favicon_service/data:ro
```

## 🚨 문제 해결

### 1. 포트 충돌
```bash
# 사용 중인 포트 확인
netstat -tulpn | grep 8300

# 기존 컨테이너 정리
docker-compose down
docker system prune -f
```

### 2. 메모리 부족
```bash
# 컨테이너 리소스 확인
docker stats

# 리소스 제한 확인
docker-compose -f docker-compose.prod.yml config
```

### 3. 빌드 실패
```bash
# 캐시 없이 재빌드
docker build --no-cache -t phishing-detector-api .

# 중간 이미지 정리
docker system prune -a
```

### 4. 모델 로딩 실패
- 모델 파일이 올바른 경로에 있는지 확인
- 볼륨 마운트 설정 확인
- 파일 권한 확인

## 🔒 보안 고려사항

1. **환경 변수**: 민감한 정보는 환경 변수로 관리
2. **네트워크**: 필요한 포트만 노출
3. **볼륨**: 읽기 전용 마운트 사용
4. **리소스 제한**: 메모리 및 CPU 제한 설정

## 📈 모니터링

### 컨테이너 상태 확인
```bash
docker-compose ps
docker stats
```

### 로그 모니터링
```bash
# 실시간 로그
docker-compose logs -f

# 특정 시간 이후 로그
docker-compose logs --since="2024-01-01T00:00:00"
```

## 🧹 정리

```bash
# 서비스 중지 및 컨테이너 제거
./docker-build.sh stop

# 모든 컨테이너 및 이미지 정리
docker-compose down --rmi all --volumes --remove-orphans
docker system prune -a
```

## 📞 지원

문제가 발생하면 다음을 확인하세요:

1. Docker 및 Docker Compose 버전
2. 시스템 리소스 (메모리, 디스크 공간)
3. 네트워크 연결
4. 로그 파일 (`./logs/` 디렉토리) 