"""
감성분석 모듈
- KoBERT 기반 감성분석 (선택적, lazy loading)
- 사전 기반 감성분석 (fallback)
- 긍정/부정/중립 3-class 분류
"""

from typing import List, Dict, Tuple, Optional
from collections import Counter
import re

# ============================================
# KoBERT 모델 (Lazy Loading)
# ============================================

MODEL_NAME = "monologg/kobert"
_tokenizer = None
_model = None
_device = None
_kobert_available = False

SENTIMENT_LABELS = {
    0: "negative",
    1: "neutral", 
    2: "positive"
}

def _load_kobert_model():
    """KoBERT 모델을 lazy loading으로 로드"""
    global _tokenizer, _model, _device, _kobert_available
    
    if _kobert_available:
        return True
    
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[KoBERT] 모델 로딩 시도 중... (Device: {_device})")
        
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_NAME,
            num_labels=3
        ).to(_device)
        _model.eval()
        
        _kobert_available = True
        print("[KoBERT] 모델 로딩 완료!")
        return True
    except Exception as e:
        print(f"[KoBERT] 모델 로딩 실패, 사전 기반 분석 사용: {e}")
        _kobert_available = False
        return False

# ============================================
# 사전 기반 감성 분석 (Fallback)
# ============================================

POSITIVE_WORDS = {
    "좋다", "좋아", "좋은", "좋네", "좋아요", "최고", "대박", "감사", "감동",
    "재밌", "재미", "재밌다", "유익", "도움", "유용", "훌륭", "멋지", "굿",
    "완벽", "사랑", "추천", "강추", "인정", "👍", "❤️", "💕", "😊", "🔥",
    "쵝오", "굿굿", "짱", "개좋", "레전드", "갓", "신의한수", "핵인싸",
    "꿀팁", "알차", "알찬", "정주행", "존경", "배우", "배워", "배웠",
    "고맙", "감사합니다", "정성", "센스", "웃", "웃겨", "웃긴", "ㅋㅋ",
    "감동적", "따뜻", "행복", "힐링", "위로", "공감", "울컥", "뭉클",
    "프로", "전문", "실력", "꼼꼼", "친절", "깔끔", "깨끗", "정확"
}

NEGATIVE_WORDS = {
    "별로", "싫다", "싫어", "최악", "지루", "짜증", "실망", "거짓", "광고",
    "시간낭비", "돈아까", "후회", "속았", "과대광고", "👎", "😡", "😢",
    "노잼", "별로야", "안좋", "구려", "형편없", "아쉽", "별로네", "실망이야",
    "뻔", "뻔하", "식상", "재미없", "지루해", "루즈", "루즈해", "장황",
    "이해안", "이해불가", "억지", "오그라", "민망", "부끄", "창피",
    "불친절", "불편", "불만", "짜증나", "화나", "열받", "어이없", "황당",
    "비추", "비추천", "추천안", "말리", "사지마", "보지마", "거르", "패스"
}

NEUTRAL_INDICATORS = {
    "그냥", "보통", "그저그래", "무난", "평범", "soso", "쏘쏘", "글쎄", "모르겠"
}

INTENSIFIERS = {
    "진짜", "정말", "너무", "엄청", "완전", "개", "핵", "존", "매우", "무척",
    "아주", "정말로", "진심", "레알", "ㄹㅇ", "오지게"
}

NEGATIONS = {
    "안", "못", "절대", "전혀", "없", "아니"
}

# ============================================
# 텍스트 전처리
# ============================================

def clean_text_for_bert(text: str) -> str:
    """BERT 입력용 텍스트 정제"""
    # URL, 멘션 제거
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#\w+', '', text)
    
    # 과도한 반복 문자 제거 (ㅋㅋㅋㅋ → ㅋㅋ)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)
    
    # 공백 정리
    text = ' '.join(text.split())
    
    return text.strip()

def analyze_sentiment_dict(text: str) -> Tuple[str, float]:
    """
    사전 기반 감성 분석 (fallback)
    """
    original_text = text
    text = clean_text_for_bert(text).lower()
    
    # 이모지 추출
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    emojis = emoji_pattern.findall(original_text)
    
    # 이모지 기반 점수
    emoji_score = 0
    for emoji in emojis:
        if emoji in {"👍", "❤️", "💕", "😊", "🔥", "😍", "🥰", "😁", "😄", "🥵"}:
            emoji_score += 2
        elif emoji in {"👎", "😡", "😢", "😭", "💔", "😞", "😠"}:
            emoji_score -= 2
    
    # 단어 기반 감성 점수
    words = text.split()
    pos_count = 0
    neg_count = 0
    
    has_intensifier = any(word in text for word in INTENSIFIERS)
    intensity_multiplier = 1.5 if has_intensifier else 1.0
    negation_count = sum(1 for word in NEGATIONS if word in text)
    
    for word in words:
        if any(pos in word for pos in POSITIVE_WORDS):
            pos_count += 1
        if any(neg in word for neg in NEGATIVE_WORDS):
            neg_count += 1
    
    # 부정어 홀수개면 감성 반전
    if negation_count % 2 == 1:
        pos_count, neg_count = neg_count, pos_count
    
    pos_score = pos_count * intensity_multiplier
    neg_score = neg_count * intensity_multiplier
    total_score = (pos_score - neg_score) + emoji_score
    
    neutral_detected = any(neutral in text for neutral in NEUTRAL_INDICATORS)
    
    if neutral_detected or abs(total_score) < 1:
        return "neutral", 0.5
    elif total_score > 0:
        confidence = min(total_score / 5, 1.0)
        return "positive", confidence
    else:
        confidence = min(abs(total_score) / 5, 1.0)
        return "negative", confidence

# ============================================
# KoBERT 감성 분석 핵심 함수
# ============================================

def analyze_sentiment_kobert(text: str) -> Tuple[str, float]:
    """
    KoBERT 기반 감성분석 (가능한 경우), 아니면 사전 기반 분석
    
    Args:
        text: 분석할 텍스트
    
    Returns:
        (감성, 확신도) 
        - 감성: "positive", "negative", "neutral"
        - 확신도: 0.0 ~ 1.0
    """
    # KoBERT 모델 로드 시도
    if not _load_kobert_model():
        # KoBERT 로드 실패 시 사전 기반 분석
        return analyze_sentiment_dict(text)
    
    # 1. 텍스트 전처리
    cleaned_text = clean_text_for_bert(text)
    
    if not cleaned_text or len(cleaned_text) < 2:
        return "neutral", 0.5
    
    try:
        import torch
        
        # 2. 토크나이징 (최대 512 토큰)
        inputs = _tokenizer(
            cleaned_text,
            return_tensors="pt",
            max_length=512,
            padding=True,
            truncation=True
        ).to(_device)
        
        # 3. 모델 추론
        with torch.no_grad():
            outputs = _model(**inputs)
            logits = outputs.logits
            
            # 4. Softmax로 확률 변환
            probabilities = torch.softmax(logits, dim=1)[0]
            
            # 5. 가장 높은 확률의 감성 선택
            predicted_class = torch.argmax(probabilities).item()
            confidence = probabilities[predicted_class].item()
            
            sentiment = SENTIMENT_LABELS[predicted_class]
            
        return sentiment, confidence
        
    except Exception as e:
        print(f"[KoBERT Error] {text[:50]}: {e}")
        # 오류 발생 시 사전 기반 분석으로 fallback
        return analyze_sentiment_dict(text)


def analyze_sentiment_kobert_batch(texts: List[str], batch_size: int = 32) -> List[Tuple[str, float]]:
    """
    대량 텍스트 배치 처리 (속도 최적화)
    
    Args:
        texts: 분석할 텍스트 리스트
        batch_size: 배치 크기
    
    Returns:
        [(감성, 확신도), ...] 리스트
    """
    # KoBERT 모델 로드 시도
    if not _load_kobert_model():
        # KoBERT 로드 실패 시 사전 기반 분석
        return [analyze_sentiment_dict(text) for text in texts]
    
    results = []
    
    # 배치 단위로 처리
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        cleaned_batch = [clean_text_for_bert(t) for t in batch]
        
        # 빈 텍스트 필터링
        valid_texts = [t for t in cleaned_batch if t and len(t) >= 2]
        
        if not valid_texts:
            results.extend([("neutral", 0.5)] * len(batch))
            continue
        
        try:
            import torch
            
            # 배치 토크나이징
            inputs = _tokenizer(
                valid_texts,
                return_tensors="pt",
                max_length=512,
                padding=True,
                truncation=True
            ).to(_device)
            
            # 배치 추론
            with torch.no_grad():
                outputs = _model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=1)
                
                # 각 샘플의 예측
                predicted_classes = torch.argmax(probabilities, dim=1)
                confidences = torch.max(probabilities, dim=1).values
                
                for pred_class, conf in zip(predicted_classes, confidences):
                    sentiment = SENTIMENT_LABELS[pred_class.item()]
                    results.append((sentiment, conf.item()))
        
        except Exception as e:
            print(f"[KoBERT Batch Error] {e}")
            # 오류 발생 시 해당 배치를 사전 기반 분석으로 fallback
            for text in batch:
                results.append(analyze_sentiment_dict(text))
    
    return results


def analyze_comments_batch_kobert(comments: List[str]) -> Dict[str, any]:
    """
    KoBERT 기반 댓글 일괄 분석
    
    Returns:
        {
            "positive": 긍정 댓글 수,
            "negative": 부정 댓글 수,
            "neutral": 중립 댓글 수,
            "positive_ratio": 긍정 비율 (%),
            "sentiment_score": 최종 감성 점수 (0-100),
            "total_comments": 전체 댓글 수,
            "examples": {...}
        }
    """
    if not comments:
        return {
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "positive_ratio": 0.0,
            "negative_ratio": 0.0,
            "neutral_ratio": 0.0,
            "sentiment_score": 50.0,
            "total_comments": 0,
            "examples": {"positive": [], "negative": []}
        }
    
    # 배치 처리로 감성 분석
    method = "KoBERT" if _kobert_available else "사전기반"
    print(f"[감성분석 {method}] {len(comments)}개 댓글 분석 중...")
    sentiment_results = analyze_sentiment_kobert_batch(comments, batch_size=32)
    
    # 결과 집계
    results = {"positive": [], "negative": [], "neutral": []}
    
    for comment, (sentiment, confidence) in zip(comments, sentiment_results):
        results[sentiment].append((comment, confidence))
    
    pos_count = len(results["positive"])
    neg_count = len(results["negative"])
    neu_count = len(results["neutral"])
    total = len(comments)
    
    # 비율 계산
    pos_ratio = (pos_count / total) * 100
    neg_ratio = (neg_count / total) * 100
    neu_ratio = (neu_count / total) * 100
    
    # 감성 점수 (0-100)
    sentiment_score = (pos_ratio - neg_ratio + 100) / 2
    sentiment_score = max(0, min(100, sentiment_score))
    
    # 대표 예시 추출 (확신도 높은 순)
    pos_examples = sorted(results["positive"], key=lambda x: x[1], reverse=True)[:5]
    neg_examples = sorted(results["negative"], key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "positive": pos_count,
        "negative": neg_count,
        "neutral": neu_count,
        "positive_ratio": round(pos_ratio, 2),
        "negative_ratio": round(neg_ratio, 2),
        "neutral_ratio": round(neu_ratio, 2),
        "sentiment_score": round(sentiment_score, 2),
        "total_comments": total,
        "examples": {
            "positive": [text[:100] for text, _ in pos_examples],
            "negative": [text[:100] for text, _ in neg_examples]
        },
        "model_info": {
            "model": MODEL_NAME if _kobert_available else "dict-based",
            "device": str(_device) if _kobert_available else "N/A",
            "batch_processing": True,
            "kobert_available": _kobert_available
        }
    }


# ============================================
# 키워드 추출 (기존 유지)
# ============================================

def extract_keywords_improved(comments: List[str], top_k: int = 20) -> List[Dict[str, any]]:
    """개선된 키워드 추출 (기존 코드 유지)"""
    STOPWORDS = {
        "있", "없", "하", "되", "이", "그", "저", "것", "수", "등", "및", "제", "약",
        "즉", "또한", "또는", "의", "가", "은", "는", "을", "를", "에", "에서"
    }
    
    all_words = []
    for comment in comments:
        clean = clean_text_for_bert(comment)
        words = [w for w in clean.split() if len(w) > 1 and w not in STOPWORDS]
        all_words.extend(words)
    
    word_counts = Counter(all_words)
    
    keywords = []
    for word, count in word_counts.most_common(top_k):
        keywords.append({
            "keyword": word,
            "count": count,
            "frequency": round(count / len(comments) * 100, 2)
        })
    
    return keywords