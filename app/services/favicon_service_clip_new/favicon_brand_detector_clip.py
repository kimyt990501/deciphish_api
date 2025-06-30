#!/usr/bin/env python3
"""
Brand Logo Matcher
브랜드 로고 매칭 시스템

CLIP + FAISS를 사용하여 입력된 로고 이미지와 가장 유사한 브랜드를 찾습니다.
"""

import json
import faiss
import torch
import numpy as np
from pathlib import Path
from PIL import Image
import torchvision.transforms as T
import clip
from typing import Dict, List, Tuple, Union, Optional
import logging
import argparse
import base64
from io import BytesIO
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 설정 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = Path(BASE_DIR) / "data" / "brand_logo.faiss"
NAMES_PATH = Path(BASE_DIR) / "data" / "brand_names.json"
METADATA_PATH = Path(BASE_DIR) / "data" / "brand_metadata.json"

# 전역 변수들 (기존 코드와의 호환성을 위해)
_brand_logo_matcher = None

def domain_in_url(url, brand_domain):
    """URL에서 브랜드 도메인 확인"""
    try:
        return brand_domain.lower() in urlparse(url).netloc.lower()
    except:
        return False

def base64_to_pil(b64_str):
    """base64 문자열을 PIL Image로 변환"""
    data = base64.b64decode(b64_str)
    return Image.open(BytesIO(data)).convert("RGB")

class BrandLogoMatcher:
    def __init__(self, index_path: Path = INDEX_PATH, 
                 names_path: Path = NAMES_PATH,
                 metadata_path: Path = METADATA_PATH):
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # CLIP 모델 로드
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        self.model.eval()
        
        # 전처리 파이프라인
        self.transform = T.Compose([
            T.Resize(224, interpolation=T.InterpolationMode.BICUBIC),
            T.CenterCrop(224),
            T.ToTensor(),
            T.Normalize(mean=[0.48145466, 0.4578275, 0.40821073],
                       std=[0.26862954, 0.26130258, 0.27577711]),
        ])
        
        # 인덱스 및 데이터 로드
        self._load_index_and_data(index_path, names_path, metadata_path)
        
    def _load_index_and_data(self, index_path: Path, names_path: Path, metadata_path: Path):
        """FAISS 인덱스와 관련 데이터 로드"""
        
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS 인덱스 파일을 찾을 수 없습니다: {index_path}")
        if not names_path.exists():
            raise FileNotFoundError(f"브랜드 이름 파일을 찾을 수 없습니다: {names_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(f"메타데이터 파일을 찾을 수 없습니다: {metadata_path}")
            
        # FAISS 인덱스 로드
        self.index = faiss.read_index(str(index_path))
        
        # 브랜드 이름들 로드
        with open(names_path, 'r', encoding='utf-8') as f:
            self.brand_names = json.load(f)
            
        # 메타데이터 로드
        with open(metadata_path, 'r', encoding='utf-8') as f:
            self.metadata = json.load(f)
        
    def preprocess_image(self, image_input: Union[str, Path, Image.Image]) -> torch.Tensor:
        """이미지 전처리"""
        if isinstance(image_input, (str, Path)):
            image = Image.open(image_input).convert('RGB')
            filename = Path(image_input).name
        elif isinstance(image_input, Image.Image):
            image = image_input.convert('RGB')
            filename = getattr(image_input, 'filename', '<memory>')
        else:
            raise ValueError("지원하지 않는 이미지 형식입니다.")
            
        tensor = self.transform(image).unsqueeze(0).to(self.device)
        return tensor, filename
        
    def encode_image(self, image_tensor: torch.Tensor) -> np.ndarray:
        """이미지를 CLIP으로 인코딩"""
        with torch.no_grad():
            features = self.model.encode_image(image_tensor).cpu().numpy()
            # L2 정규화 (코사인 유사도를 위해)
            features = features / np.linalg.norm(features, axis=1, keepdims=True)
            return features.astype('float32')
    
    def search_similar_brands(self, query_embedding: np.ndarray, k: int = 5) -> Tuple[List[float], List[int]]:
        """FAISS 인덱스에서 유사한 브랜드 검색"""
        distances, indices = self.index.search(query_embedding, k)
        return distances[0].tolist(), indices[0].tolist()
    
    def predict(self, image_input: Union[str, Path, Image.Image], k: int = 5, 
                threshold: float = 0.7) -> Dict:
        """
        브랜드 로고 예측
        
        Args:
            image_input: 이미지 파일 경로 또는 PIL Image 객체
            k: 반환할 상위 결과 개수
            threshold: 신뢰도 임계값 (코사인 유사도)
            
        Returns:
            예측 결과 딕셔너리
        """
        
        # 1. 이미지 전처리
        image_tensor, filename = self.preprocess_image(image_input)
        
        # 2. CLIP 인코딩
        query_embedding = self.encode_image(image_tensor)
        
        # 3. 유사 브랜드 검색
        similarities, indices = self.search_similar_brands(query_embedding, k)
        
        # 4. 결과 구성
        results = []
        for sim, idx in zip(similarities, indices):
            if idx < len(self.brand_names) and idx < len(self.metadata):
                brand_info = self.metadata[idx]
                results.append({
                    'brand_name': brand_info['name'],
                    'domain': brand_info['domain'],
                    'similarity': float(sim),
                    'confidence': 'high' if sim >= threshold else 'low',
                    'alias': brand_info.get('alias', []),
                    'favicon_path': brand_info.get('favicon_path', ''),
                    'index': idx
                })
        
        # 5. 최고 예측 결과
        top_result = results[0] if results else None
        is_confident = top_result and top_result['similarity'] >= threshold
        
        return {
            'query_image': filename,
            'predicted_brand': top_result['brand_name'] if top_result else 'Unknown',
            'predicted_domain': top_result['domain'] if top_result else 'Unknown',
            'top_similarity': top_result['similarity'] if top_result else 0.0,
            'is_confident': is_confident,
            'threshold_used': threshold,
            'top_k_results': results
        }
    
    def predict_batch(self, image_list: List[Union[str, Path, Image.Image]], 
                     k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """배치 예측"""
        results = []
        
        for i, image_input in enumerate(image_list):
            try:
                result = self.predict(image_input, k, threshold)
                results.append(result)
            except Exception as e:
                results.append({
                    'query_image': str(image_input),
                    'error': str(e),
                    'predicted_brand': 'Error',
                    'predicted_domain': 'Error',
                    'top_similarity': 0.0,
                    'is_confident': False
                })
        
        return results
    
    def find_brand_by_name(self, brand_name: str) -> Optional[Dict]:
        """브랜드 이름으로 메타데이터 검색"""
        brand_name_lower = brand_name.lower()
        
        for metadata in self.metadata:
            if metadata['name'].lower() == brand_name_lower:
                return metadata
                
            # 별명에서도 검색
            for alias in metadata.get('alias', []):
                if alias.lower() == brand_name_lower:
                    return metadata
                    
        return None
    
    def get_stats(self) -> Dict:
        """인덱스 통계 정보"""
        return {
            'total_brands': len(self.brand_names),
            'index_dimension': self.index.d,
            'index_vectors': self.index.ntotal,
            'device': self.device,
            'model': 'ViT-B/32'
        }
    
    def detect_brand_from_favicon(self, favicon_base64: str, url: str = "", threshold: float = 0.99) -> Optional[Dict]:
        """
        파비콘에서 브랜드 탐지 (기존 인터페이스 호환)
        
        Args:
            favicon_base64: 파비콘 이미지 (Base64 인코딩)
            url: 웹페이지 URL (도메인 매칭용)
            threshold: 유사도 임계값 (기본값을 0.7로 변경)
            
        Returns:
            탐지된 브랜드 정보 또는 None
        """
        try:
            # 파비콘 이미지 변환
            favicon_img = base64_to_pil(favicon_base64)
            
            # 브랜드 예측
            result = self.predict(favicon_img, k=5, threshold=threshold)
            
            # 상위 결과 로그 출력 (임계값 통과 여부와 관계없이)
            if result.get('top_k_results'):
                print(f"파비콘 탐지 상위 결과 (임계값: {threshold}):")
                for i, res in enumerate(result['top_k_results'][:3], 1):
                    print(f"  {i}. {res['brand_name']}: {res['similarity']:.4f} ({'✓' if res['similarity'] >= threshold else '✗'})")
            
            if result['is_confident'] and result['top_similarity'] >= threshold:
                top_result = result['top_k_results'][0]
                
                # 도메인 매칭 확인
                domain_match_result = domain_in_url(url, top_result['domain'])
                confidence = "high" if domain_match_result else "medium"
                reason = "exact_match_domain_match" if domain_match_result else "exact_match_domain_mismatch"
                
                return {
                    "name": top_result['brand_name'],
                    "domain": top_result['domain'],
                    "similarity": top_result['similarity'],
                    "method": "faiss_clip_embedding_new",
                    "confidence": confidence,
                    "reason": reason
                }
            else:
                # 임계값 미달 시 상세 정보 출력
                best_match = result.get('top_k_results', [{}])[0] if result.get('top_k_results') else {}
                best_similarity = best_match.get('similarity', 0.0)
                best_brand = best_match.get('brand_name', 'Unknown')
                print(f"임계값 미달: 최고 매치 '{best_brand}' (유사도: {best_similarity:.4f} < {threshold})")
            
            return None
            
        except Exception as e:
            print(f"파비콘 탐지 중 오류 발생: {e}")
            return None

def _get_brand_logo_matcher():
    """전역 브랜드 로고 매처 인스턴스 반환 (지연 로딩)"""
    global _brand_logo_matcher
    if _brand_logo_matcher is None:
        _brand_logo_matcher = BrandLogoMatcher()
    return _brand_logo_matcher

def detect_brand_from_favicon(favicon_base64: str, url: str = "", threshold: float = 0.7) -> Optional[Dict]:
    """
    파비콘에서 브랜드 탐지 (기존 함수 인터페이스 호환)
    """
    matcher = _get_brand_logo_matcher()
    return matcher.detect_brand_from_favicon(favicon_base64, url, threshold)

class FaviconBrandDetector:
    """파비콘 기반 브랜드 탐지기 (기존 클래스 인터페이스 호환)"""
    
    def __init__(self):
        self.matcher = None
    
    def _get_matcher(self):
        """매처 인스턴스를 지연 로딩으로 가져오기"""
        if self.matcher is None:
            self.matcher = BrandLogoMatcher()
        return self.matcher
    
    def detect_brand_from_favicon(self, favicon_base64: str, url: str = "", threshold: float = 0.7) -> Optional[Dict]:
        """파비콘에서 브랜드 탐지"""
        matcher = self._get_matcher()
        return matcher.detect_brand_from_favicon(favicon_base64, url, threshold)

# 전역 인스턴스
favicon_detector = None

def get_favicon_detector():
    """전역 파비콘 탐지기 인스턴스 반환"""
    global favicon_detector
    if favicon_detector is None:
        favicon_detector = FaviconBrandDetector()
    return favicon_detector

def main():
    """CLI 인터페이스"""
    parser = argparse.ArgumentParser(description="브랜드 로고 매칭 시스템")
    parser.add_argument('--image', '-i', required=True, help='예측할 이미지 파일 경로')
    parser.add_argument('--top-k', '-k', type=int, default=5, help='상위 K개 결과 (기본: 5)')
    parser.add_argument('--threshold', '-t', type=float, default=0.7, help='신뢰도 임계값 (기본: 0.7)')
    parser.add_argument('--verbose', '-v', action='store_true', help='상세 출력')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # 매처 초기화
        matcher = BrandLogoMatcher()
        
        # 예측 실행
        result = matcher.predict(args.image, k=args.top_k, threshold=args.threshold)
        
        # 간단한 결과 출력
        print(f"예측 브랜드: {result['predicted_brand']} (유사도: {result['top_similarity']:.3f})")
        
        if args.verbose:
            print(f"도메인: {result['predicted_domain']}")
            print(f"신뢰도: {'높음' if result['is_confident'] else '낮음'}")
            for i, res in enumerate(result['top_k_results'][:3], 1):
                print(f"{i}. {res['brand_name']} ({res['similarity']:.3f})")
            stats = matcher.get_stats()
            print(f"총 브랜드 수: {stats['total_brands']}")
                
    except Exception as e:
        logger.error(f"오류 발생: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    exit(main()) 