class PhishingDetectorException(Exception):
    """기본 예외 클래스"""
    pass

class DatabaseConnectionError(PhishingDetectorException):
    """데이터베이스 연결 오류"""
    pass

class BrandDataError(PhishingDetectorException):
    """브랜드 데이터 관련 오류"""
    pass

class DetectionError(PhishingDetectorException):
    """탐지 과정에서 발생한 오류"""
    pass 