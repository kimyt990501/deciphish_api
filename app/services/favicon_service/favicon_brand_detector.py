import warnings
import logging
warnings.filterwarnings("ignore")
logging.getLogger("fvcore.common.checkpoint").setLevel(logging.ERROR)
logging.getLogger("detectron2").setLevel(logging.ERROR)

import base64
import json
import torch
import clip
import faiss
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from urllib.parse import urlparse
import os
from typing import Dict, Optional

# 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "./data/embedding/faiss_logo.index")
META_PATH = os.path.join(BASE_DIR, "./data/embedding/brand_meta.json")
DISTANCE_THRESHOLD = 0.4
device = "cuda" if torch.cuda.is_available() else "cpu"

# 모델을 지연 로딩으로 변경
_clip_model = None
_preprocess = None
_faiss_index = None
_brand_meta = None

def _load_clip_model():
    """CLIP 모델을 필요할 때만 로드"""
    global _clip_model, _preprocess
    if _clip_model is None or _preprocess is None:
        _clip_model, _preprocess = clip.load("ViT-B/32", device=device)
    return _clip_model, _preprocess

def _load_faiss_data():
    """FAISS 인덱스와 브랜드 메타데이터를 필요할 때만 로드"""
    global _faiss_index, _brand_meta
    if _faiss_index is None or _brand_meta is None:
        _faiss_index = faiss.read_index(INDEX_PATH)
        _brand_meta = json.load(open(META_PATH, "r", encoding="utf-8"))
    return _faiss_index, _brand_meta

def domain_in_url(url, brand_domain):
    try:
        return brand_domain.lower() in urlparse(url).netloc.lower()
    except:
        return False

# base64 → PIL
def base64_to_pil(b64_str):
    data = base64.b64decode(b64_str)
    return Image.open(BytesIO(data)).convert("RGB")

# CLIP 임베딩 (PIL 기준)
def extract_clip_embedding_from_pil(pil_img):
    clip_model, preprocess = _load_clip_model()
    image = preprocess(pil_img).unsqueeze(0).to(device)
    with torch.no_grad():
        emb = clip_model.encode_image(image)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.cpu().squeeze(0).numpy().astype("float32")

# FAISS 검색 (기존 로직과 동일)
def search_brand(embedding, top_k=5):
    faiss_index, brand_meta = _load_faiss_data()
    D, I = faiss_index.search(np.expand_dims(embedding, axis=0), top_k)
    
    results = []
    for i in range(top_k):
        idx = I[0][i]
        results.append({
            "name": brand_meta["names"][idx],
            "domain": brand_meta["domains"][idx],
            "favicon": brand_meta["favicons"][idx],
            "distance": float(D[0][i]),
            "rank": i + 1
        })
    
    return results

# 개선된 로고 매칭 함수 (기존 로직과 동일)
def match_logo_with_threshold(embedding, url, strict_threshold=0.3, loose_threshold=0.5):
    """
    엄격한 임계값과 느슨한 임계값을 사용한 2단계 매칭
    """
    candidates = search_brand(embedding, top_k=5)
    
    # 1단계: 엄격한 임계값으로 정확한 매칭
    for candidate in candidates:
        if candidate["distance"] <= strict_threshold:
            if domain_in_url(url, candidate["domain"]):
                return {"match": candidate, "confidence": "high", "reason": "exact_match_domain_match"}
            else:
                return {"match": candidate, "confidence": "high", "reason": "exact_match_domain_mismatch"}
    
    # 2단계: 느슨한 임계값으로 유사한 매칭
    for candidate in candidates:
        if candidate["distance"] <= loose_threshold:
            if domain_in_url(url, candidate["domain"]):
                return {"match": candidate, "confidence": "medium", "reason": "similar_match_domain_match"}
            else:
                return {"match": candidate, "confidence": "medium", "reason": "similar_match_domain_mismatch"}
    
    # 매칭 실패
    return {"match": candidates[0] if candidates else None, "confidence": "low", "reason": "no_match"}

def detect_brand_from_favicon(favicon_base64: str, url: str = "", threshold: float = 0.999) -> Optional[Dict]:
    """
    파비콘에서 브랜드 탐지 (기존 logo_brand_extractor 로직 사용)
    
    Args:
        favicon_base64: 파비콘 이미지 (Base64 인코딩)
        url: 웹페이지 URL (도메인 매칭용)
        threshold: 유사도 임계값
        
    Returns:
        탐지된 브랜드 정보 또는 None
    """
    try:
        # 파비콘 이미지 변환
        favicon_img = base64_to_pil(favicon_base64)
        
        # CLIP 임베딩 추출
        emb = extract_clip_embedding_from_pil(favicon_img)
        
        # 브랜드 매칭 - threshold를 거리로 변환 (유사도 0.999 = 거리 0.001)
        distance_threshold = 1.0 - threshold
        result = match_logo_with_threshold(emb, url, strict_threshold=distance_threshold, loose_threshold=distance_threshold)
        
        if result["confidence"] in ["high", "medium"]:
            match = result["match"]
            similarity = 1.0 - match["distance"]
            
            # 유사도가 threshold 이상인 경우만 반환
            if similarity >= threshold:
                return {
                    "name": match["name"],
                    "domain": match["domain"],
                    "similarity": similarity,
                    "method": "faiss_clip_embedding",
                    "confidence": result["confidence"],
                    "reason": result["reason"]
                }
        
        return None
        
    except Exception as e:
        print(f"파비콘 브랜드 탐지 실패: {e}")
        return None

# 전역 인스턴스
favicon_detector = None

def get_favicon_detector():
    """전역 파비콘 탐지기 인스턴스 반환"""
    global favicon_detector
    if favicon_detector is None:
        favicon_detector = FaviconBrandDetector()
    return favicon_detector

class FaviconBrandDetector:
    """파비콘 기반 브랜드 탐지기 (기존 로직 래퍼)"""
    
    def __init__(self):
        pass
    
    def detect_brand_from_favicon(self, favicon_base64: str, url: str = "", threshold: float = 0.7) -> Optional[Dict]:
        """파비콘에서 브랜드 탐지"""
        return detect_brand_from_favicon(favicon_base64, url, threshold) 