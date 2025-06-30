# DeciPhish API

고급 AI 기반 피싱 사이트 탐지 시스템으로, 다중 검증 방식을 통해 높은 정확도의 피싱 탐지를 제공합니다.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-supported-blue.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 주요 기능

### 다중 레이어 피싱 탐지
- **URL 리다이렉트 추적**: 의심스러운 리다이렉트 패턴 탐지
- **파비콘 분석**: CLIP 모델 기반 브랜드 로고 인식
- **텍스트 분석**: Gemini LLM을 활용한 페이지 콘텐츠 분석
- **도메인 패턴 분석**: 무료 DNS, IP 주소, 무작위 문자열 탐지

### 고급 보안 기능
- **화이트리스트 검증**: 신뢰할 수 있는 도메인 자동 인식
- **브랜드 데이터베이스**: 10,000+ 브랜드 정보 관리
- **실시간 캐싱**: 빠른 응답을 위한 지능형 캐시 시스템
- **사용자 인증**: JWT 기반 보안 인증

### 관리 및 모니터링
- **탐지 히스토리**: 모든 검사 결과 추적 및 분석
- **사용자 관리**: 계정 생성, 권한 관리, 세션 관리
- **API 문서**: 자동 생성되는 Swagger/OpenAPI 문서

## 기술 스택

### Backend
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **MySQL**: 관계형 데이터베이스
- **SQLAlchemy**: ORM 및 데이터베이스 연결
- **JWT**: 토큰 기반 인증

### AI/ML 모델
- **CLIP**: 파비콘 이미지 분석 및 브랜드 인식
- **Gemini API**: 자연어 처리 및 텍스트 분석
- **Custom CRP Classifier**: 피싱 패턴 분류

### Infrastructure
- **Docker**: 컨테이너화 및 배포
- **Docker Compose**: 다중 서비스 오케스트레이션
- **Nginx**: 리버스 프록시 (선택사항)

## 빠른 시작

### Prerequisites
- Docker & Docker Compose
- Python 3.8+
- MySQL 8.0+

### 1. 저장소 클론
```bash
git clone https://github.com/yourusername/phishing-detector-api.git
cd phishing-detector-api
```

### 2. 환경 변수 설정
```bash
cp env.example .env
```

`.env` 파일을 편집하여 필요한 설정을 입력하세요:

```env
# 데이터베이스 설정
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=phishing_user
MYSQL_PASSWORD=your_secure_password
MYSQL_DB=phishing_detector

# API 키
GEMINI_API_KEY=your_gemini_api_key
HUGGINGFACE_API_KEY=your_huggingface_api_key

# JWT 설정
JWT_SECRET_KEY=your_super_secret_jwt_key
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# 환경 설정
ENVIRONMENT=production
DEBUG=false
```

### 3. Docker로 실행

Docker 빌드 및 실행을 위한 전용 스크립트를 제공합니다:

```bash
# 스크립트 실행 권한 부여
chmod +x docker-build.sh

# 개발 환경 실행 (권장)
./docker-build.sh dev

# 운영 환경 실행
./docker-build.sh prod

# phpMyAdmin 포함 개발 환경 (DB 관리 시 유용)
./docker-build.sh dev-phpmyadmin

# 운영 환경 + phpMyAdmin
./docker-build.sh prod-phpmyadmin
```

#### 기타 유용한 명령어:
```bash
# 이미지만 빌드
./docker-build.sh build

# 서비스 중지
./docker-build.sh stop

# 로그 확인
./docker-build.sh logs

# 컨테이너 상태 확인
./docker-build.sh status

# 도움말
./docker-build.sh help
```

### 4. AI 모델 다운로드 및 설정

> **⚠️ 중요**: Docker 실행 전에 반드시 AI 모델을 배치해야 합니다.

DeciPhish는 AI 기반 피싱 탐지를 위해 사전 훈련된 모델들을 사용합니다.

#### 필요한 모델들:
1. **CRP Classifier (XLM-RoBERTa)**: 약 1.2GB - 피싱 패턴 분류용
2. **CLIP 모델**: 파비콘 브랜드 인식용
3. **브랜드 임베딩 데이터**: 브랜드 벡터 데이터

#### 훈련된 모델 배치 방법:

사전에 훈련된 모델 파일들을 다음 위치에 배치하세요:

```
# 1. CRP Classifier 모델
app/services/crp_classifier/models/crp_model_xlm-roberta-base/
├── config.json
├── model.safetensors
├── sentencepiece.bpe.model
├── special_tokens_map.json
├── tokenizer_config.json
└── tokenizer.json

# 2. CLIP 브랜드 인식 데이터
app/services/favicon_service_clip_new/data/
├── brand_logo.faiss
├── brand_metadata.json
└── brand_names.json

# 3. 브랜드 임베딩 데이터
app/services/favicon_service_clip_new/data/embedding/
└── (브랜드 임베딩 파일들)
```

> **📝 참고**: 
> - 모델 파일은 크기가 크기 때문에 GitHub 저장소에는 포함되지 않습니다
> - 훈련된 모델이 없으면 기본 기능만 작동하며, AI 기반 탐지는 비활성화됩니다
> - 모델 파일이 누락된 경우 해당 기능은 자동으로 건너뛰어집니다

### 5. 데이터베이스 초기화
```bash
# 컨테이너가 실행된 후 브랜드 데이터 로드
# 개발 환경인 경우
docker-compose exec app python -c "
from app.core.brand_loader import brand_loader
import asyncio
asyncio.run(brand_loader.load_brands())
"

# 운영 환경인 경우
docker-compose -f docker-compose.prod.yml exec app python -c "
from app.core.brand_loader import brand_loader
import asyncio
asyncio.run(brand_loader.load_brands())
"
```

### 6. API 접속
- **API 문서**: http://localhost:8300/docs
- **Redoc**: http://localhost:8300/redoc
- **헬스체크**: http://localhost:8300/api/v1/health

## API 사용법

### 인증
모든 API 요청에는 JWT 토큰이 필요합니다.

```bash
# 1. 사용자 등록
curl -X POST "http://localhost:8300/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "securepassword123",
    "full_name": "Test User"
  }'

# 2. 로그인
curl -X POST "http://localhost:8300/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "securepassword123"
  }'
```

### 피싱 탐지

```bash
# Base64 인코딩된 데이터로 피싱 탐지
curl -X POST "http://localhost:8300/api/v1/detect-phishing/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://suspicious-site.com",
    "html": "base64_encoded_html",
    "favicon": "base64_encoded_favicon"
  }'

# 간단한 URL 기반 피싱 탐지
curl -X POST "http://localhost:8300/api/v1/check_phish_simple" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://suspicious-site.com"
  }'
```

### 응답 예시

```json
{
  "is_phish": 1,
  "reason": "suspicious_redirect: 무작위 문자열 패턴의 서브도메인",
  "detected_brand": null,
  "original_url": "https://jaergfv3.duckdns.org",
  "final_url": "https://www.apple.com",
  "redirect_analysis": {
    "has_redirect": true,
    "redirect_count": 1,
    "suspicious_original": true,
    "suspicious_reason": "무작위 문자열 패턴의 서브도메인",
    "redirect_chain": [
      "https://jaergfv3.duckdns.org",
      "https://www.apple.com"
    ]
  }
}
```

## 프로젝트 구조

```
phishing_detector_api_new/
├── app/
│   ├── api/
│   │   └── endpoints.py              # API 엔드포인트 정의
│   ├── core/
│   │   ├── auth_middleware.py        # JWT 인증 미들웨어
│   │   ├── config.py                 # 설정 관리
│   │   ├── database.py               # 데이터베이스 연결
│   │   ├── logger.py                 # 로깅 설정
│   │   └── whitelist.py              # 화이트리스트 관리
│   ├── pipeline/
│   │   └── phishing_pipeline.py      # 메인 피싱 탐지 파이프라인
│   ├── services/
│   │   ├── auth_service.py           # 사용자 인증 서비스
│   │   ├── brand_service.py          # 브랜드 관리 서비스
│   │   ├── crp_classifier/           # CRP 분류 모델
│   │   ├── favicon_service_clip_new/ # CLIP 기반 파비콘 분석
│   │   ├── text_extractor_gemini/    # Gemini 텍스트 분석
│   │   ├── detector_service.py       # 탐지 서비스
│   │   └── search_service.py         # 도메인 검색 서비스
│   └── main.py                       # FastAPI 애플리케이션 진입점
├── mysql/
│   └── init/                         # 데이터베이스 초기화 스크립트
├── docker-compose.yml               # 개발용 Docker 설정
├── docker-compose.prod.yml          # 프로덕션용 Docker 설정
├── Dockerfile.optimized             # 최적화된 Docker 이미지
└── requirements.txt                 # Python 의존성
```

## 개발 가이드

### 로컬 개발 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=password
# ... 기타 환경변수

# 개발 서버 실행
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8300
```

### 테스트 실행

```bash
# 단위 테스트
pytest tests/

# 커버리지 테스트
pytest --cov=app tests/
```

### 코드 품질 도구

```bash
# 코드 포맷팅
black app/
isort app/

# 린팅
flake8 app/
pylint app/
```

## 성능 최적화

### 캐싱 전략
- **결과 캐싱**: 24시간 동안 탐지 결과 저장
- **브랜드 데이터 캐싱**: 메모리 내 브랜드 정보 캐시
- **API 응답 캐싱**: 중복 요청 최적화

### 타임아웃 설정
- **HTTP 요청**: 3초 타임아웃
- **도메인 접근성 검사**: 최대 6개 도메인 시도
- **검색 엔진 쿼리**: 상위 3개 결과만 확인

## AI 모델 정보

### CRP Classifier
- **모델**: XLM-RoBERTa-base 기반 커스텀 분류기
- **용도**: 피싱 페이지의 credential request patterns 탐지
- **크기**: 약 1.2GB
- **언어**: 다국어 지원

### CLIP 기반 파비콘 분석
- **모델**: OpenAI CLIP
- **용도**: 파비콘 이미지에서 브랜드 로고 인식
- **정확도**: 98% 임계값으로 브랜드 매칭

### 브랜드 데이터베이스
- **브랜드 수**: 10,000+ 글로벌 브랜드
- **벡터 임베딩**: FAISS 인덱스 기반 고속 검색
- **업데이트**: 신규 브랜드 자동 학습 및 추가

> **중요**: 모델 파일이 없으면 AI 기반 탐지 기능이 제한됩니다. 기본적인 URL 패턴 분석과 화이트리스트 검증만 작동합니다.

## 보안 고려사항

### 입력 검증
- URL 형식 검증
- XSS 방지를 위한 HTML 이스케이핑
- SQL 인젝션 방지

### 인증 및 권한
- JWT 토큰 기반 인증
- 역할 기반 접근 제어 (RBAC)
- 세션 관리 및 토큰 무효화

### 데이터 보호
- 비밀번호 해싱 (bcrypt)
- API 키 환경변수 관리
- HTTPS 강제 사용 권장

## 배포 가이드

### Docker 배포

```bash
# 프로덕션 이미지 빌드
docker build -f Dockerfile.optimized -t phishing-detector:latest .

# 프로덕션 환경 실행
docker-compose -f docker-compose.prod.yml up -d
```

### 환경별 설정

```yaml
# docker-compose.prod.yml 예시
version: '3.8'
services:
  app:
    image: phishing-detector:latest
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
```

## 모니터링 및 로깅

### 로그 파일
- `logs/phishing_detector.log`: 메인 애플리케이션 로그
- `logs/server.log`: 서버 액세스 로그

### 헬스체크 엔드포인트
```bash
curl http://localhost:8300/api/v1/health
```

### 통계 API
```bash
# 탐지 통계 조회
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8300/api/v1/statistics

# 사용자별 히스토리
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8300/api/v1/my-history
```