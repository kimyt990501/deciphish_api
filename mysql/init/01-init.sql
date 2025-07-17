-- 피싱 탐지 API 데이터베이스 초기화 스크립트

-- 데이터베이스 생성 (이미 환경변수로 생성됨)
-- CREATE DATABASE IF NOT EXISTS phishing_detector;
-- USE phishing_detector;

-- 사용자 테이블 (먼저 생성 - 다른 테이블에서 참조함)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role ENUM('admin', 'user', 'viewer') DEFAULT 'user',
    is_active TINYINT(1) DEFAULT 1,
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_username (username),
    UNIQUE KEY unique_email (email),
    INDEX idx_role (role),
    INDEX idx_active (is_active)
);

-- 브랜드 정보 테이블
CREATE TABLE IF NOT EXISTS brands (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    domain VARCHAR(255) NOT NULL,
    description TEXT,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_name (name),
    INDEX idx_domain (domain),
    INDEX idx_active (is_active)
);

-- 피싱 탐지 결과 테이블 (users 테이블 생성 후)
CREATE TABLE IF NOT EXISTS phishing_detections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    url TEXT NOT NULL,
    is_phish TINYINT(1) NOT NULL,
    is_redirect TINYINT(1) DEFAULT 0,
    redirect_url TEXT,
    is_crp TINYINT(1) DEFAULT 0,
    reason VARCHAR(100),
    detected_brand VARCHAR(100),
    confidence FLOAT,
    html_content LONGTEXT,
    favicon_base64 LONGTEXT,
    screenshot_base64 LONGTEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_url (url(255)),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at),
    INDEX idx_is_phish (is_phish),
    INDEX idx_detected_brand (detected_brand)
);

-- API 요청 로그 테이블
CREATE TABLE IF NOT EXISTS api_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    endpoint VARCHAR(50) NOT NULL,
    method VARCHAR(10) NOT NULL,
    url VARCHAR(500),
    status_code INT,
    response_time_ms INT,
    user_agent TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_endpoint (endpoint),
    INDEX idx_created_at (created_at),
    INDEX idx_status_code (status_code)
);

-- 사용자 세션 테이블
CREATE TABLE IF NOT EXISTS user_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_token (token_hash),
    INDEX idx_user_id (user_id),
    INDEX idx_expires (expires_at),
    INDEX idx_active (is_active)
);

-- API 키 테이블 (선택적)
CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    key_name VARCHAR(100) NOT NULL,
    api_key VARCHAR(255) NOT NULL,
    permissions JSON,
    rate_limit_per_hour INT DEFAULT 1000,
    is_active TINYINT(1) DEFAULT 1,
    last_used TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_api_key (api_key),
    INDEX idx_user_id (user_id),
    INDEX idx_active (is_active)
);

-- 기본 관리자 계정 생성 (비밀번호: admin123)
INSERT INTO users (username, email, password_hash, full_name, role) VALUES 
('admin', 'admin@phishingdetector.com', '$2b$12$TbYoz0GAFRC8RxwUvtDfSeY.LvcaaAmvVV.ztEcV0iMFv8MIVOme2', 'System Administrator', 'admin')
ON DUPLICATE KEY UPDATE username=username;

INSERT INTO users (username, email, password_hash, full_name, role) VALUES 
('testuser', 'test@example.com', '$2b$12$m0FB2I8D0b6kN4aUulElx.3NHeCeTQDmH93cilRGPX/umMw7UBna6', 'Test User', 'user')
ON DUPLICATE KEY UPDATE username=username;

-- 테이블 생성 확인
SHOW TABLES; 