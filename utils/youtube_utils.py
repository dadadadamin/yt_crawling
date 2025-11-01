import os, time, httpx,csv
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

# 키워드 기반 채널 ID 검색
def search_channels_by_keyword(keyword: str, top_n: int, region: str = "KR", lang: str = "ko") -> List[str]:
    """
    키워드로 채널을 검색하여 ID 목록 반환 (Search: list API)
    """
    ids, page_token = [], None

    # API 호출 횟수를 줄이기 위해 maxResult 50 설정
    while len(ids) < top_n:
        params = {
            "part": "snippet",
            "type": "channel",
            "q": keyword,
            "maxResults": min(50, top_n - len(ids) + 20), # 넉넉하게 요청
            "key": API_KEY,
            "order": "relevance", # 관련도 순
            "regionCode": region,
            "relevanceLanguage": lang
        }
        if page_token:
            params["pageToken"] = page_token

        data = safe_get(SEARCH_URL, params)

        # 채널 ID만 추출
        for item in data.get("items", []):
            ch = item.get("id", {}).get("channelId")
            if ch and ch not in ids:
                ids.append(ch)
                if len(ids) >= top_n:
                    break # 목표한 10개를 채우면 중단

        page_token = data.get("nextPageToken")
        if not page_token:
            break # 다음 페이지가 없으면 중단
        sleep_short()
    
    return ids[:top_n] # 정확히 top_n 개수만큼 잘라서 반환


# 인기 영상 기반 채널 수집

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

# 채널의 최신 영상 통계 목록 '가져오기'
def get_recent_video_stats(channel_id: str, num_videos: int = 5):
    """
    채널의 최신 N개 영상 통계를 리스트로 반환 (API 호출)
    """
    from models.youtube_models import VideoStatsOut # 함수 내에서 import
    
    try:
        # 1. 채널의 업로드 플레이리스트 ID 가져오기
        playlist_id = get_uploads_playlist_id(channel_id)
        if not playlist_id:
            return []

        # 2. 최신 N개 영상 ID 가져오기
        video_ids = get_recent_video_ids(playlist_id, max_results=num_videos)
        if not video_ids:
            return []

        # 3. N개 영상의 통계 가져오기
        stats = get_video_stats(video_ids) # List[VideoStatsOut]
        return stats
    
    except Exception as e:
        print(f"[Error] get_recent_video_stats 실패 (Channel: {channel_id}): {e}")
        return []

# '가져온 통계'로 참여율 '계산하기'
def calculate_engagement_rate_from_stats(stats: list, subscriber_count: int) -> float | None:
    """
    (API 호출 없음) 영상 통계 리스트(stats)와 구독자 수로 참여율(%) 계산
    """
    if not subscriber_count or subscriber_count == 0:
        return None # 구독자 없으면 계산 불가
    if not stats:
        return 0.0

    # 평균 (좋아요 + 댓글 수) 계산
    total_likes = 0
    total_comments = 0
    for s in stats:
        total_likes += (s.like_count or 0)
        total_comments += (s.comment_count or 0)

    if len(stats) == 0:
        return 0.0

    avg_engagement = (total_likes + total_comments) / len(stats)
    
    # 참여율 = (평균 참여) / 구독자 수 * 100
    rate = (avg_engagement / subscriber_count) * 100
    return round(rate, 2) # 소수점 2자리까지

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

# <최신 업로드 1개(가장 최근 영상) ID/제목 가져오기>
def get_latest_video_info(channel_id: str) -> Optional[Dict[str, str]]:
    """
    채널의 업로드 재생목록에서 '가장 최근' 영상 1개의 video_id와 제목을 반환
    """
    up = get_uploads_playlist_id(channel_id)
    if not up:
        return None

    # playlistItems는 최신이 먼저 오므로 maxResults=1
    params = {
        "part": "contentDetails",
        "playlistId": up,
        "maxResults": 1,
        "key": API_KEY,
    }
    data = safe_get(PLAYLIST_ITEMS_URL, params)
    items = data.get("items", [])
    if not items:
        return None
    vid = items[0].get("contentDetails", {}).get("videoId")
    if not vid:
        return None

    # 제목은 videos.list로 1회 조회
    vinfo = safe_get(VIDEOS_URL, {"part": "snippet", "id": vid, "key": API_KEY})
    title = None
    if vinfo.get("items"):
        title = (vinfo["items"][0].get("snippet") or {}).get("title")

    return {"video_id": vid, "video_title": title}


def save_comments_to_csv(rows: List[Dict[str, Any]], out_dir: str, base_name: str) -> str:
    """
    rows를 CSV로 저장. 파일 경로를 반환.
    """
    os.makedirs(out_dir, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in base_name)[:60]
    path = os.path.join(out_dir, f"{safe_name}.csv")

    # rows 예시 키: video_id, comment_id, parent_id, author, text, like_count, published_at
    fieldnames = ["video_id", "comment_id", "parent_id", "author", "text", "like_count", "published_at"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "video_id": r.get("video_id"),
                "comment_id": r.get("comment_id"),
                "parent_id": r.get("parent_id"),
                "author": r.get("author"),
                "text": r.get("text"),
                "like_count": r.get("like_count"),
                "published_at": r.get("published_at"),
            })
    return path


def analyze_comments_keywords(texts: List[str], top_k: int = 40) -> List[Dict[str, Any]]:
    """
    간단 빈도 기반 키워드 추출. (한글/영문 공백 기준 토큰화)
    필요 시 불용어 처리/형태소 분석으로 고도화 가능.
    """
    # 너무 짧은/공백 문자열 제거
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return []

    tokens = " ".join(cleaned).split()
    from collections import Counter
    common = Counter(tokens).most_common(top_k)
    return [{"keyword": k, "score": float(c), "method": "freq"} for k, c in common]


def fetch_comments_structured_for_video(
    video_id: str,
    include_replies: bool = False,
    max_total: int = 500
) -> list[dict]:
    """
    commentThreads.list를 이용해
    - 특정 영상의 댓글(+선택적으로 대댓글)을 구조화해서 수집합니다.
    - 반환: [{video_id, comment_id, parent_id, author, text, like_count, published_at}, ...]
    """
    texts = []
    fetched = 0
    page_token = None

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
            # 상위 댓글
            top = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}) or {}
            comment_id = thread.get("id")
            texts.append({
                "video_id": video_id,
                "comment_id": comment_id,
                "parent_id": None,
                "author": top.get("authorDisplayName"),
                "text": top.get("textDisplay"),
                "like_count": top.get("likeCount"),
                "published_at": top.get("publishedAt"),
            })
            fetched += 1

            # 대댓글 수집 옵션
            if include_replies:
                replies = (thread.get("replies", {}) or {}).get("comments", []) or []
                for rep in replies:
                    r_snip = rep.get("snippet", {}) or {}
                    texts.append({
                        "video_id": video_id,
                        "comment_id": rep.get("id"),
                        "parent_id": comment_id,
                        "author": r_snip.get("authorDisplayName"),
                        "text": r_snip.get("textDisplay"),
                        "like_count": r_snip.get("likeCount"),
                        "published_at": r_snip.get("publishedAt"),
                    })
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

#현재 테스트용 
#초기화면 유튜버 구성 구독자 수 100만 이상 유튜버들 나열 
def filter_large_channels(channels: list, min_subs: int = 1000000):
    """
    구독자 수 기준으로 필터링.
    channels: ChannelDetails 리스트
    min_subs: 최소 구독자 수 (기본 100만)
    """
    return [
        ch for ch in channels
        if ch.subscriber_count is not None and ch.subscriber_count >= min_subs
    ]
#기업 유튜버 제외 시나리오
def is_personnal_channel(ch)->bool:
    '''휴리스틱 필터
    ch:ChennelDetails
    '''
    title=(ch.title or"").lower()
    desc=(ch.description or"").lower()

    #키워드 기반 제외
    corp_kw=[
        "official","channel","music","news","entertainment", "company", "corporation","record",
        "group","media","press","공식","뉴스","엔터","방송","레코드","기획사","agency","jyp","yg","sm","hybe","cj"
    ]
    if any(kw in title for kw in corp_kw):
        return False
    if any(desc in title for kw in corp_kw):
        return False
    
    #영상수로 제외 (영상 1만개당 구독자 100만이면 제외)
    if ch.subscriber_count and ch.video_count:
        ratio=ch.video_count/ch.subscriber_count #영상 수/구독자 수
        if ratio>0.01:
            return False
        
    #토픽 기반 제외
    if ch.topic_ids:
        joined=",".join(ch.topic_ids).lower()
        if any(k in joined for k in["music","tv","corporation"]):
            return False
    #국가 필터
    if ch.country and ch.country and ch.country!="KR":
        return False
    
    return True

