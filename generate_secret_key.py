#!/usr/bin/env python3
"""
JWT 시크릿 키 생성 도구

사용법:
    python generate_secret_key.py
"""

import secrets
import string

def generate_strong_secret_key(length: int = 64) -> str:
    """강력한 시크릿 키 생성"""
    # URL-safe base64 인코딩된 랜덤 문자열 생성
    return secrets.token_urlsafe(length)

def generate_password(length: int = 16) -> str:
    """강력한 비밀번호 생성"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

if __name__ == "__main__":
    print("=== JWT 시크릿 키 생성 도구 ===\n")
    
    # JWT 시크릿 키 생성
    jwt_secret = generate_strong_secret_key(64)
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print(f"길이: {len(jwt_secret)} 문자\n")
    
    # 데이터베이스 비밀번호 생성
    db_password = generate_password(20)
    print(f"MySQL 비밀번호 예시: {db_password}")
    print(f"길이: {len(db_password)} 문자\n")
    
    print("=== .env 파일 설정 예시 ===")
    print(f"""
# JWT 인증 설정
JWT_SECRET_KEY={jwt_secret}

# 데이터베이스 설정
MYSQL_PASSWORD={db_password}

# 기타 보안 설정
ENVIRONMENT=production
DEBUG=false
""")
    
    print("\n⚠️  중요: 생성된 키들을 안전한 곳에 보관하세요!")
    print("⚠️  프로덕션 환경에서는 이 키들을 절대 공개하지 마세요!") 