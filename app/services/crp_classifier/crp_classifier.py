import torch
from transformers import XLMRobertaTokenizer, XLMRobertaForSequenceClassification
import os

# 현재 파일의 디렉토리를 기준으로 모델 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(current_dir, "models", "crp_model_xlm-roberta-base")

# 모델을 지연 로딩으로 변경
_tokenizer = None
_model = None

def _load_model():
    """모델을 필요할 때만 로드"""
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        _tokenizer = XLMRobertaTokenizer.from_pretrained(MODEL_PATH)
        _model = XLMRobertaForSequenceClassification.from_pretrained(MODEL_PATH)
        _model.eval()
    return _tokenizer, _model

def crp_classifier(url: str, cleaned_html: str) -> bool:
    """
    Return True if CRP detected, else False
    """
    tokenizer, model = _load_model()
    
    inputs = tokenizer(
        cleaned_html,
        return_tensors="pt",
        max_length=512,
        truncation=True,
        padding="max_length"
    )

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.softmax(logits, dim=1)
        pred = torch.argmax(probs, dim=1).item()

    return pred == 1