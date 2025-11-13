"""
YouTube 데이터 분석 관련 유틸리티
- 키워드 추출
- 감성 분석
- 참여율 계산
- 채널 필터링
"""
from typing import List, Dict, Any, Optional
from collections import Counter
from statistics import mean

from utils.youtube_api import (
    get_uploads_playlist_id,
    get_recent_video_ids,
    get_video_stats,
)


def extract_keywords_tfidf(texts: List[str], top_k: int) -> List[Dict[str, Any]]:
    """빈도 기반 키워드 추출"""
    tokens = " ".join(texts).split()
    common = Counter(tokens).most_common(top_k)
    return [{"keyword": k, "score": float(c), "method": "freq"} for k, c in common]


def analyze_comments_keywords(texts: List[str], top_k: int = 40) -> List[Dict[str, Any]]:
    """댓글 키워드 분석 (빈도 기반)"""
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return []

    tokens = " ".join(cleaned).split()
    common = Counter(tokens).most_common(top_k)
    return [{"keyword": k, "score": float(c), "method": "freq"} for k, c in common]


# 감성 분석용 키워드
_POS = {"좋다", "감사", "최고", "재밌", "유익", "사랑", "추천", "대박", "멋지", "굿", "좋아요"}
_NEG = {"별로", "싫다", "최악", "지루", "짜증", "실망", "거짓", "광고", "시간낭비"}


def basic_sentiment_summary(texts: List[str]) -> Dict[str, Any]:
    """기본 감성 분석"""
    pos = neg = neu = 0
    pos_ex, neg_ex = [], []
    for t in texts:
        if any(w in t for w in _POS):
            pos += 1
            if len(pos_ex) < 5: 
                pos_ex.append(t[:80])
        elif any(w in t for w in _NEG):
            neg += 1
            if len(neg_ex) < 5: 
                neg_ex.append(t[:80])
        else:
            neu += 1
    return {"positive": pos, "neutral": neu, "negative": neg,
            "examples": {"positive": pos_ex, "negative": neg_ex}}


def calculate_engagement_rate_from_stats(stats: list, subscriber_count: int) -> float | None:
    """영상 통계 리스트와 구독자 수로 참여율(%) 계산"""
    if not subscriber_count or subscriber_count == 0:
        return None
    if not stats:
        return 0.0

    total_likes = 0
    total_comments = 0
    for s in stats:
        total_likes += (s.like_count or 0)
        total_comments += (s.comment_count or 0)

    if len(stats) == 0:
        return 0.0

    avg_engagement = (total_likes + total_comments) / len(stats)
    rate = (avg_engagement / subscriber_count) * 100
    return round(rate, 2)


def compute_channel_engagement_rate(channel_id: str, max_videos: int = 8) -> Optional[float]:
    """채널 참여율 계산"""
    up = get_uploads_playlist_id(channel_id)
    if not up: 
        return None
    vids = get_recent_video_ids(up, max_results=max_videos)
    if not vids: 
        return None
    stats = get_video_stats(vids)
    rates = []
    for v in stats:
        views = v.view_count or 0
        likes = v.like_count or 0
        comments = v.comment_count or 0
        if views > 0:
            rates.append((likes + comments) / views * 100.0)
    return round(mean(rates), 2) if rates else None


def attach_metrics_to_channels(details: list) -> list:
    """ChannelDetails 리스트에 engagement_rate, roi를 붙여 ChannelWithMetrics로 변환"""
    from models.youtube_models import ChannelWithMetrics
    out: list[ChannelWithMetrics] = []
    for ch in details:
        try:
            er = compute_channel_engagement_rate(ch.channel_id, max_videos=8)
        except Exception:
            er = None
        roi_placeholder = float(ch.subscriber_count or 0)
        out.append(ChannelWithMetrics(
            **ch.model_dump(),
            engagement_rate=er,
            roi=roi_placeholder
        ))
    return out


def filter_large_channels(channels: list, min_subs: int = 1000000):
    """구독자 수 기준 필터링"""
    return [
        ch for ch in channels
        if ch.subscriber_count is not None and ch.subscriber_count >= min_subs
    ]


def is_personnal_channel(ch) -> bool:
    """개인 채널 여부 판단 (휴리스틱 필터)"""
    title = (ch.title or "").lower()
    desc = (ch.description or "").lower()

    # 키워드 기반 제외
    corp_kw = [
        "official", "channel", "music", "news", "entertainment", "company", 
        "corporation", "record", "group", "media", "press", "공식", "뉴스", 
        "엔터", "방송", "레코드", "기획사", "agency", "jyp", "yg", "sm", "hybe", "cj"
    ]
    if any(kw in title for kw in corp_kw):
        return False
    if any(kw in desc for kw in corp_kw):
        return False
    
    # 영상수로 제외
    if ch.subscriber_count and ch.video_count:
        ratio = ch.video_count / ch.subscriber_count
        if ratio > 0.01:
            return False
        
    # 토픽 기반 제외
    if ch.topic_ids:
        joined = ",".join(ch.topic_ids).lower()
        if any(k in joined for k in ["music", "tv", "corporation"]):
            return False
    
    # 국가 필터
    if ch.country and ch.country != "KR":
        return False
    
    return True

