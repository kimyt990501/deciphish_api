"""
QR 코드 처리 서비스

QR 코드에서 URL 추출 및 QR 코드 생성 기능을 제공합니다.
"""

import cv2
import numpy as np
from PIL import Image
import io
import qrcode
import base64
from urllib.parse import urlparse
from typing import Optional, Tuple
from pyzbar import pyzbar
from app.core.logger import logger


class QRService:
    """QR 코드 처리 서비스"""
    
    ALLOWED_CONTENT_TYPES = {
        "image/png",
        "image/jpeg", 
        "image/jpg",
        "image/bmp",
        "image/webp",
        "image/gif",
    }
    
    def __init__(self, logo_path: Optional[str] = None):
        self.logo_path = logo_path
    
    def is_valid_image(self, file_bytes: bytes) -> bool:
        """이미지 파일이 유효한지 확인"""
        try:
            Image.open(io.BytesIO(file_bytes)).verify()
            return True
        except Exception as e:
            logger.error(f"Invalid image: {e}")
            return False
    
    def is_probable_url(self, text: str) -> bool:
        """문자열이 URL 형태인지 확인"""
        if text.startswith("http://") or text.startswith("https://"):
            return True
        
        # http/https가 없는 경우 도메인 형태인지 확인
        parsed = urlparse("http://" + text)
        return parsed.hostname is not None and "." in parsed.hostname
    
    def ensure_https_prefix(self, text: str) -> str:
        """URL에 https 프로토콜이 없으면 추가"""
        if not text.startswith("http://") and not text.startswith("https://"):
            return "https://" + text
        return text
    
    async def extract_url_from_qr_image(self, image_bytes: bytes) -> str:
        """
        QR 코드 이미지에서 URL 추출
        
        Args:
            image_bytes: QR 코드 이미지 바이트
            
        Returns:
            추출된 URL
            
        Raises:
            ValueError: QR 코드 인식 실패 또는 URL이 아닌 경우
        """
        try:
            # 이미지 유효성 검사
            if not self.is_valid_image(image_bytes):
                raise ValueError("올바른 이미지 파일이 아닙니다")
            
            # numpy 배열로 변환
            img_np = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
            
            if image is None:
                raise ValueError("이미지를 읽을 수 없습니다")
            
            # OpenCV QR 코드 디텍터 사용
            qr_detector = cv2.QRCodeDetector()
            data, bbox, _ = qr_detector.detectAndDecode(image)
            
            # OpenCV로 안되면 pyzbar로 시도
            if not data:
                logger.info("OpenCV QR detection failed, trying pyzbar")
                pil_image = Image.open(io.BytesIO(image_bytes))
                decoded_objects = pyzbar.decode(pil_image)
                
                if decoded_objects:
                    data = decoded_objects[0].data.decode('utf-8')
            
            if not data:
                raise ValueError("QR 코드를 인식할 수 없습니다")
            
            logger.info(f"QR 코드에서 추출된 데이터: {data}")
            
            # URL 형태인지 확인
            if not self.is_probable_url(data):
                raise ValueError("QR 코드에 URL이 포함되어 있지 않습니다")
            
            # https 프로토콜 추가
            url = self.ensure_https_prefix(data)
            logger.info(f"최종 추출된 URL: {url}")
            
            return url
            
        except Exception as e:
            logger.error(f"QR 코드 URL 추출 실패: {e}")
            raise ValueError(f"QR 코드 처리 실패: {str(e)}")
    
    async def generate_qr_code_with_logo(self, text: str, logo_path: Optional[str] = None) -> str:
        """
        로고가 포함된 QR 코드 생성
        
        Args:
            text: QR 코드에 포함할 텍스트 (URL)
            logo_path: 로고 이미지 경로 (선택사항)
            
        Returns:
            Base64 인코딩된 QR 코드 이미지 (data URL 형태)
        """
        try:
            # QR 코드 생성
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,  # 높은 복원률
                box_size=10,
                border=4,
            )
            qr.add_data(text)
            qr.make(fit=True)
            
            # QR 코드 이미지 생성
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            
            # 로고 삽입 (로고 경로가 제공된 경우)
            used_logo_path = logo_path or self.logo_path
            if used_logo_path:
                try:
                    # 로고 이미지 불러오기
                    logo_img = Image.open(used_logo_path)
                    
                    # 로고 크기 조절 (QR 코드의 20%)
                    qr_width, qr_height = qr_img.size
                    logo_size = int(qr_width * 0.2)
                    logo_img = logo_img.resize((logo_size, logo_size), Image.LANCZOS)
                    
                    # 로고를 QR 코드 중앙에 삽입
                    pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                    
                    # 투명도 지원을 위해 RGBA 모드 사용
                    if logo_img.mode != 'RGBA':
                        logo_img = logo_img.convert('RGBA')
                    
                    qr_img.paste(logo_img, pos, mask=logo_img)
                    logger.info(f"로고가 포함된 QR 코드 생성 완료: {used_logo_path}")
                    
                except Exception as e:
                    logger.warning(f"로고 삽입 실패, 로고 없는 QR 코드 생성: {e}")
            
            # Base64 인코딩
            buffered = io.BytesIO()
            qr_img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            logger.info(f"QR 코드 생성 완료: {text}")
            return f"data:image/png;base64,{img_base64}"
            
        except Exception as e:
            logger.error(f"QR 코드 생성 실패: {e}")
            raise ValueError(f"QR 코드 생성 실패: {str(e)}")


# 전역 QR 서비스 인스턴스
qr_service = QRService()

# 로고 경로 설정 함수 (나중에 설정에서 불러올 수 있도록)
def set_logo_path(logo_path: str):
    """QR 서비스의 로고 경로 설정"""
    global qr_service
    qr_service.logo_path = logo_path 