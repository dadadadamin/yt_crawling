import os, time, httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from typing import List, Dict, Any, Optional
from collections import Counter
from statistics import mean

load_dotenv()
API_KEY = os.getenv("YT_API_KEY")
if not API_KEY:
    raise RuntimeError("환경변수 YT_API_KEY가 없습니다. (.env에 YT_API_KEY=YOUR_KEY 추가)")

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

def sleep_short():
    time.sleep(0.2)

def safe_get(url: str, params: dict) -> dict:
    with httpx.Client(timeout=20) as client:
        r = client.get(url, params=params)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()

def fetch_channel_details(channel_ids: List[str], source_tag: str):
    from models.youtube_models import ChannelDetails
    rows: List[ChannelDetails] = []
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        params = {
            "part": "snippet,statistics,brandingSettings,topicDetails",
            "id": ",".join(batch),
            "key": API_KEY,
        }
        data = safe_get(CHANNELS_URL, params)
        for item in data.get("items", []):
            snippet = item.get("snippet", {}) or {}
            stats = item.get("statistics", {}) or {}
            branding = (item.get("brandingSettings", {}) or {}).get("channel", {}) or {}
            topics = (item.get("topicDetails", {}) or {}).get("topicCategories", []) or []
            thumbs = (snippet.get("thumbnails") or {})
            thumb_url = (thumbs.get("high") or thumbs.get("default") or {}).get("url")
            country = snippet.get("country") or branding.get("country")
            rows.append(ChannelDetails(
                channel_id=item.get("id"),
                title=snippet.get("title"),
                description=snippet.get("description"),
                custom_url=snippet.get("customUrl"),
                published_at=snippet.get("publishedAt"),
                country=country,
                subscriber_count=int(stats["subscriberCount"]) if "subscriberCount" in stats else None,
                video_count=int(stats["videoCount"]) if "videoCount" in stats else None,
                view_count=int(stats["viewCount"]) if "viewCount" in stats else None,
                topic_ids=topics or None,
                thumbnail_url=thumb_url,
                source=source_tag
            ))
        sleep_short()
    return rows

def collect_channels_from_most_popular(region_code: str = "KR", pages: int = 5) -> List[str]:
    ch_ids = set()
    page_token, seen = None, 0
    while seen < pages:
        params = {"part": "snippet", "chart": "mostPopular", "regionCode": region_code,
                  "maxResults": 50, "key": API_KEY}
        if page_token: params["pageToken"] = page_token
        data = safe_get(VIDEOS_URL, params)
        for item in data.get("items", []):
            sn = item.get("snippet", {}) or {}
            if sn.get("channelId"): ch_ids.add(sn["channelId"])
        page_token = data.get("nextPageToken")
        seen += 1
        if not page_token: break
        sleep_short()
    return list(ch_ids)

def get_uploads_playlist_id(channel_id: str) -> Optional[str]:
    params = {"part": "contentDetails", "id": channel_id, "key": API_KEY}
    data = safe_get(CHANNELS_URL, params)
    items = data.get("items", [])
    if not items: return None
    return items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

def get_recent_video_ids(uploads_playlist_id: str, max_results: int) -> List[str]:
    video_ids, page_token = [], None
    while len(video_ids) < max_results:
        params = {"part": "contentDetails", "playlistId": uploads_playlist_id,
                  "maxResults": min(50, max_results - len(video_ids)), "key": API_KEY}
        if page_token: params["pageToken"] = page_token
        data = safe_get(PLAYLIST_ITEMS_URL, params)
        for it in data.get("items", []):
            vid = it.get("contentDetails", {}).get("videoId")
            if vid: video_ids.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token: break
        sleep_short()
    return video_ids

def get_video_stats(video_ids: List[str]):
    from models.youtube_models import VideoStatsOut
    rows: List[VideoStatsOut] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        params = {"part": "snippet,statistics", "id": ",".join(batch), "key": API_KEY}
        data = safe_get(VIDEOS_URL, params)
        for item in data.get("items", []):
            sn, st = item.get("snippet", {}) or {}, item.get("statistics", {}) or {}
            rows.append(VideoStatsOut(
                video_id=item.get("id"),
                video_title=sn.get("title"),
                video_published_at=sn.get("publishedAt"),
                view_count=int(st["viewCount"]) if "viewCount" in st else None,
                like_count=int(st["likeCount"]) if "likeCount" in st else None,
                comment_count=int(st["commentCount"]) if "commentCount" in st else None,
            ))
        sleep_short()
    return rows

def fetch_all_comments_for_video(video_id: str, include_replies: bool, max_total: int) -> List[str]:
    texts, fetched, page_token = [], 0, None
    while True:
        params = {"part": "snippet,replies", "videoId": video_id, "maxResults": 100,
                  "textFormat": "plainText", "key": API_KEY}
        if page_token: params["pageToken"] = page_token
        data = safe_get(COMMENT_THREADS_URL, params)
        for thread in data.get("items", []):
            top = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}) or {}
            if top.get("textDisplay"): texts.append(top["textDisplay"])
            fetched += 1
            if include_replies:
                replies = thread.get("replies", {}).get("comments", []) or []
                for rep in replies:
                    rs = rep.get("snippet", {}) or {}
                    if rs.get("textDisplay"): texts.append(rs["textDisplay"])
                    fetched += 1
            if fetched >= max_total: break
        if fetched >= max_total: break
        page_token = data.get("nextPageToken")
        if not page_token: break
        sleep_short()
    return texts

def extract_keywords_tfidf(texts: List[str], top_k: int) -> List[Dict[str, Any]]:
    tokens = " ".join(texts).split()
    common = Counter(tokens).most_common(top_k)
    return [{"keyword": k, "score": float(c), "method": "freq"} for k, c in common]

_POS = {"좋다", "감사", "최고", "재밌", "유익", "사랑", "추천", "대박", "멋지", "굿", "좋아요"}
_NEG = {"별로", "싫다", "최악", "지루", "짜증", "실망", "거짓", "광고", "시간낭비"}

def basic_sentiment_summary(texts: List[str]) -> Dict[str, Any]:
    pos = neg = neu = 0
    pos_ex, neg_ex = [], []
    for t in texts:
        if any(w in t for w in _POS):
            pos += 1
            if len(pos_ex) < 5: pos_ex.append(t[:80])
        elif any(w in t for w in _NEG):
            neg += 1
            if len(neg_ex) < 5: neg_ex.append(t[:80])
        else:
            neu += 1
    return {"positive": pos, "neutral": neu, "negative": neg,
            "examples": {"positive": pos_ex, "negative": neg_ex}}

def compute_channel_engagement_rate(channel_id: str, max_videos: int = 8) -> Optional[float]:
    up = get_uploads_playlist_id(channel_id)
    if not up: return None
    vids = get_recent_video_ids(up, max_results=max_videos)
    if not vids: return None
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
    """
    ChannelDetails 리스트에 engagement_rate, roi(임시: subscriber_count)를 붙여
    ChannelWithMetrics로 변환해서 반환.
    """
    from models.youtube_models import ChannelWithMetrics
    out: list[ChannelWithMetrics] = []
    for ch in details:
        try:
            er = compute_channel_engagement_rate(ch.channel_id, max_videos=8)
        except Exception:
            er = None
        roi_placeholder = float(ch.subscriber_count or 0)  # 임시 ROI = 구독자수
        out.append(ChannelWithMetrics(
            **ch.model_dump(),
            engagement_rate=er,
            roi=roi_placeholder
        ))
    return out
