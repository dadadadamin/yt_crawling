"""
감성분석 모듈
- 한국어 감성 사전 기반 분석
- 긍정/부정/중립 분류
- 점수화 (0-100)
"""

from typing import List, Dict, Tuple
from collections import Counter
import re

# ============================================
# 한국어 감성 사전 
# ============================================

POSITIVE_WORDS = {
    # 기본 긍정어
    "좋다", "좋아", "좋은", "좋네", "좋아요", "최고", "대박", "감사", "감동",
    "재밌", "재미", "재밌다", "유익", "도움", "유용", "훌륭", "멋지", "굿",
    "완벽", "사랑", "추천", "강추", "인정", "👍", "❤️", "💕", "😊", "🔥",
    
    # 추가 긍정어
    "쵝오", "굿굿", "짱", "개좋", "레전드", "갓", "신의한수", "핵인싸",
    "꿀팁", "알차", "알찬", "정주행", "존경", "배우", "배워", "배웠",
    "고맙", "감사합니다", "정성", "센스", "웃", "웃겨", "웃긴", "ㅋㅋ",
    "감동적", "따뜻", "행복", "힐링", "위로", "공감", "울컥", "뭉클",
    "프로", "전문", "실력", "꼼꼼", "친절", "깔끔", "깨끗", "정확"
}

NEGATIVE_WORDS = {
    # 기본 부정어
    "별로", "싫다", "싫어", "최악", "지루", "짜증", "실망", "거짓", "광고",
    "시간낭비", "돈아까", "후회", "속았", "과대광고", "👎", "😡", "😢",
    
    # 추가 부정어
    "노잼", "별로야", "안좋", "구려", "형편없", "아쉽", "별로네", "실망이야",
    "뻔", "뻔하", "식상", "재미없", "지루해", "루즈", "루즈해", "장황",
    "이해안", "이해불가", "억지", "오그라", "민망", "부끄", "창피",
    "불친절", "불편", "불만", "짜증나", "화나", "열받", "어이없", "황당",
    "비추", "비추천", "추천안", "말리", "사지마", "보지마", "거르", "패스"
}

NEUTRAL_INDICATORS = {
    "그냥", "보통", "그저그래", "무난", "평범", "soso", "쏘쏘", "글쎄", "모르겠"
}

# 강조 표현
INTENSIFIERS = {
    "진짜", "정말", "너무", "엄청", "완전", "개", "핵", "존", "매우", "무척",
    "아주", "정말로", "진심", "레알", "ㄹㅇ", "오지게"
}

# 부정 표현 (부정의 부정 = 긍정)
NEGATIONS = {
    "안", "못", "절대", "전혀", "없", "아니"
}

# ============================================
# 텍스트 전처리
# ============================================

def clean_text(text: str) -> str:
    """댓글 텍스트 정제"""
    # 이모지 제거 (단, 감성 분석용 이모지는 미리 추출)
    text = re.sub(r'http\S+', '', text)  # URL 제거
    text = re.sub(r'@\w+', '', text)  # 멘션 제거
    text = re.sub(r'#\w+', '', text)  # 해시태그 제거
    text = re.sub(r'[^\w\s가-힣ㄱ-ㅎㅏ-ㅣ!?.,]', '', text)  # 특수문자 제거
    text = ' '.join(text.split())  # 공백 정리
    return text.lower()

def extract_emojis(text: str) -> List[str]:
    """이모지 추출"""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 감정
        "\U0001F300-\U0001F5FF"  # 심볼
        "\U0001F680-\U0001F6FF"  # 교통
        "\U0001F1E0-\U0001F1FF"  # 국기
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.findall(text)

# ============================================
# 감성 분석 핵심 함수
# ============================================

def analyze_sentiment_advanced(text: str) -> Tuple[str, float]:
    """
    고도화된 감성분석

    Returns:
        (감성, 확신도) - 감성: "positive", "nagative", "neutral", 확신도: 0-1
    """
    original_text = text
    text = clean_text(text)
    emojis = extract_emojis(original_text)

    # 1. 이모지 기반 감성 판단
    emoji_score = 0
    for emoji in emojis:
        if emoji in {"👍", "❤️", "💕", "😊", "🔥", "😍", "🥰", "😁", "😄","🥵"}:
            emoji_score += 2
        elif emoji in {"👎", "😡", "😢", "😭", "💔", "😞", "😠"}:
            emoji_score -= 2
        
    # 2. 단어 기반 감성 점수
    words = text.split()
    pos_count = 0
    neg_count = 0

    # 강조어 감지
    has_intensifier = any(word in text for word in INTENSIFIERS)
    intensity_multiplier = 1.5 if has_intensifier else 1.0

    # 부정어 감지
    negation_count = sum(1 for word in NEGATIONS if word in text)

    for word in words:
        if any(pos in word for pos in POSITIVE_WORDS):
            pos_count += 1
        if any(neg in word for neg in NEGATIVE_WORDS):
            neg_count += 1
    
    # 부정어가 홀수개면 감성 반전
    if negation_count % 2 == 1:
        pos_count, neg_count = neg_count, pos_count

     # 강조어 적용
    pos_score = pos_count * intensity_multiplier
    neg_score = neg_count * intensity_multiplier

    # 3. 최종 점수 계산
    total_score = (pos_score - neg_score) + emoji_score

     # 4. 중립 판단
    neutral_detected = any(neutral in text for neutral in NEUTRAL_INDICATORS)

    # 5. 감성 결정
    if neutral_detected or abs(total_score) < 1:
        return "neutral", 0.5
    elif total_score > 0:
        confidence = min(total_score / 5, 1.0)  # 최대 1.0
        return "positive", confidence
    else:
        confidence = min(abs(total_score) / 5, 1.0)
        return "negative", confidence

def analyze_comments_batch(comments: List[str]) -> Dict[str, any]:
    """
    댓글 리스트를 일괄 분석

    Returns:
        {
            "positive": 긍정 댓글 수,
            "negative": 부정 댓글 수,
            "neutral": 중립 댓글 수,
            "positive_ratio": 긍정 비율 (%),
            "sentiment_score": 최종 감성 점수 (0-100),
            "total_comments": 전체 댓글 수,
            "examples": {
                "positive": [...],
                "negative": [...]
            }
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
    
    results = {"positive": [], "negative": [], "neutral": []}

    for comment in comments: 
        sentiment, confidence = analyze_sentiment_advanced(comment)
        results[sentiment].append(comment, confidence)

    pos_count = len(results["positive"])
    neg_count = len(results["negative"])
    neu_count = len(results["neutral"])
    total = len(comments)

    # 비율 계산
    pos_ratio = (pos_count / total) * 100
    neg_ratio = (neg_count / total) * 100
    neu_ratio = (neu_count / total) * 100

    # 감성 점수 (0-100)
    # 긍정 많을수록 100에 가까움, 부정 많을수록 0에 가까움
    sentiment_score = (pos_ratio - neg_ratio + 100) / 2
    sentiment_score = max(0, min(100, sentiment_score)) # 0-100 범위로 제한

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
        }
    }

# ============================================
# 키워드 추출 
# ============================================

def extract_keywords_improved(comments: List[str], top_k: int = 20) -> List[Dict[str, any]]:
    """
    개선된 키워드 추출
    - 불용어 제거
    - 명사 우선 추출
    - 감성 키워드 분리
    """
    # 한국어 불용어
    STOPWORDS = {
        "있", "없", "하", "되", "이", "그", "저", "것", "수", "등", "및", "제", "약",
        "즉", "및", "또한", "또는", "의", "가", "이", "은", "는", "을", "를", "에",
        "에서", "으로", "로", "과", "와", "한", "할", "하다", "되다"
    }
    
    all_words = []
    for comment in comments:
        clean = clean_text(comment)
        words = [w for w in clean.split() if len(w) > 1 and w not in STOPWORDS]
        all_words.extend(words)
    
    # 빈도수 계산
    word_counts = Counter(all_words)
    
    # 감성 단어 제외하고 순수 키워드만
    keywords = []
    for word, count in word_counts.most_common(top_k * 2):
        # 감성 단어가 아닌 것만 추출
        if not any(w in word for w in POSITIVE_WORDS | NEGATIVE_WORDS):
            keywords.append({
                "keyword": word,
                "count": count,
                "frequency": round(count / len(comments) * 100, 2)
            })
            
            if len(keywords) >= top_k:
                break
    
    return keywords