from urllib.parse import urlparse

def extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower()