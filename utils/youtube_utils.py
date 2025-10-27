import os, time, httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer

# .env 로드 (YT_API_KEY 사용)
load_dotenv()
API_KEY = os.getenv("YT_API_KEY")
if not API_KEY:
    raise RuntimeError("환경변수 YT_API_KEY가 없습니다. (.env에 YT_API_KEY=YOUR_KEY 추가)")

# YouTube Data API 엔드포인트
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

def sleep_short():
    """연속 호출 간 0.2초 대기(쿼터/속도 보호)"""
    time.sleep(0.2)

def safe_get(url: str, params: dict) -> dict:
    """httpx로 GET 요청하고, 4xx/5xx는 FastAPI HTTPException으로 변환"""
    with httpx.Client(timeout=20) as client:
        r = client.get(url, params=params)
        if r.status_code >= 400:
            # 개발 중엔 원문을 그대로 detail로 전달 → 디버깅 용이
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()


# 채널 상세 조회

def fetch_channel_details(channel_ids: List[str], source_tag: str):
    """channels.list 로 채널 상세(썸네일/통계/토픽) 일괄 조회"""
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

# 인기 영상 기반 채널 수집

def collect_channels_from_most_popular(region_code: str = "KR", pages: int = 5) -> List[str]:
    """videos.list(chart=mostPopular)로 인기 영상에서 channelId를 수집"""
    ch_ids = set()
    page_token, seen = None, 0
    while seen < pages:
        params = {
            "part": "snippet",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": 50,
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        data = safe_get(VIDEOS_URL, params)
        for item in data.get("items", []):
            sn = item.get("snippet", {}) or {}
            if sn.get("channelId"):
                ch_ids.add(sn["channelId"])

        page_token = data.get("nextPageToken")
        seen += 1
        if not page_token:
            break
        sleep_short()

    return list(ch_ids)

# 채널 업로드 재생목록 → 최근 영상 ID
def get_uploads_playlist_id(channel_id: str) -> str | None:
    """채널의 업로드 재생목록 ID(contentDetails.relatedPlaylists.uploads) 조회"""
    params = {"part": "contentDetails", "id": channel_id, "key": API_KEY}
    data = safe_get(CHANNELS_URL, params)
    items = data.get("items", [])
    if not items:
        return None
    return items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

def get_recent_video_ids(uploads_playlist_id: str, max_results: int) -> List[str]:
    """업로드 재생목록에서 최근 N개 영상 ID 수집 (페이지네이션 포함)"""
    video_ids, page_token = [], None
    while len(video_ids) < max_results:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": min(50, max_results - len(video_ids)),
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        data = safe_get(PLAYLIST_ITEMS_URL, params)
        for it in data.get("items", []):
            vid = it.get("contentDetails", {}).get("videoId")
            if vid:
                video_ids.append(vid)

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        sleep_short()
    return video_ids

# 영상 통계 조회
def get_video_stats(video_ids: List[str]):
    """videos.list 로 조회수/좋아요/댓글 수 등 영상 통계 일괄 조회"""
    from models.youtube_models import VideoStatsOut
    rows: List[VideoStatsOut] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        params = {
            "part": "snippet,statistics",
            "id": ",".join(batch),
            "key": API_KEY,
        }
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


# 댓글 수집
def fetch_all_comments_for_video(video_id: str, include_replies: bool, max_total: int) -> List[str]:
    """commentThreads.list 로 상위 댓글(+옵션: 대댓글) 수집 후 텍스트 리스트 반환"""
    texts, fetched, page_token = [], 0, None
    while True:
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "textFormat": "plainText",
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        data = safe_get(COMMENT_THREADS_URL, params)

        for thread in data.get("items", []):
            top = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}) or {}
            if top.get("textDisplay"):
                texts.append(top["textDisplay"])
            fetched += 1

            if include_replies:
                replies = thread.get("replies", {}).get("comments", []) or []
                for rep in replies:
                    rs = rep.get("snippet", {}) or {}
                    if rs.get("textDisplay"):
                        texts.append(rs["textDisplay"])
                    fetched += 1

            if fetched >= max_total:
                break

        if fetched >= max_total:
            break

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        sleep_short()

    return texts

# 키워드 추출 (TF-IDF)
def extract_keywords_tfidf(texts: List[str], top_k: int) -> List[Dict[str, Any]]:
    """
    최소 전처리(영문/숫자/공백 기반)로 TF-IDF 스코어 상위 토큰 반환
    - 한국어 형태소 분석까지 필요하면 kiwipiepy 연동 버전으로 확장 가능
    """
    # 간단하게 공백 토큰 기준으로도 충분히 트렌드 키워드가 잡힘
    vec = TfidfVectorizer(max_features=5000, min_df=max(2, int(len(texts) * 0.002)))
    X = vec.fit_transform([t.strip() for t in texts if t and len(t.strip()) > 0])
    scores = X.sum(axis=0).A1
    terms = vec.get_feature_names_out()
    ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)[:top_k]
    return [{"keyword": k, "score": float(s), "method": "tfidf"} for k, s in ranked]

# 아주 기본적인 감성 요약(룰 기반)
_POS = {"좋다", "감사", "최고", "재밌", "유익", "사랑", "추천", "대박", "멋지", "굿", "좋아요"}
_NEG = {"별로", "싫다", "최악", "지루", "짜증", "실망", "거짓", "광고", "시간낭비"}

def basic_sentiment_summary(texts: List[str]) -> Dict[str, Any]:
    """
    간단 키워드 매칭으로 긍/부/중립 카운트(빠르고 가벼움)
    - 정확한 모델 기반이 필요하면 HuggingFace/KoBERT 연동 고려
    """
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
    return {
        "positive": pos,
        "neutral": neu,
        "negative": neg,
        "examples": {"positive": pos_ex, "negative": neg_ex},
    }
