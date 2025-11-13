"""
YouTube Data API 호출 관련 유틸리티
"""
import os
import time
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from typing import List, Dict, Any, Optional

load_dotenv()
API_KEY = os.getenv("YT_API_KEY")
if not API_KEY:
    raise RuntimeError("환경변수 YT_API_KEY가 없습니다. (.env에 YT_API_KEY=YOUR_KEY 추가)")

# YouTube API URLs
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


def sleep_short():
    """API 호출 간 짧은 대기 시간"""
    time.sleep(0.2)


def safe_get(url: str, params: dict) -> dict:
    """안전한 HTTP GET 요청"""
    with httpx.Client(timeout=20) as client:
        r = client.get(url, params=params)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()


def fetch_channel_details(channel_ids: List[str], source_tag: str):
    """채널 상세 정보 조회"""
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


def search_channels_by_keyword(keyword: str, top_n: int, region: str = "KR", lang: str = "ko") -> List[str]:
    """키워드로 채널을 검색하여 ID 목록 반환"""
    ids, page_token = [], None

    while len(ids) < top_n:
        params = {
            "part": "snippet",
            "type": "channel",
            "q": keyword,
            "maxResults": min(50, top_n - len(ids) + 20),
            "key": API_KEY,
            "order": "relevance",
            "regionCode": region,
            "relevanceLanguage": lang
        }
        if page_token:
            params["pageToken"] = page_token

        data = safe_get(SEARCH_URL, params)

        for item in data.get("items", []):
            ch = item.get("id", {}).get("channelId")
            if ch and ch not in ids:
                ids.append(ch)
                if len(ids) >= top_n:
                    break

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        sleep_short()
    
    return ids[:top_n]


def collect_channels_from_most_popular(region_code: str = "KR", pages: int = 5) -> List[str]:
    """인기 영상 기반 채널 수집"""
    ch_ids = set()
    page_token, seen = None, 0
    while seen < pages:
        params = {"part": "snippet", "chart": "mostPopular", "regionCode": region_code,
                  "maxResults": 50, "key": API_KEY}
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


def get_uploads_playlist_id(channel_id: str) -> Optional[str]:
    """채널의 업로드 재생목록 ID 조회"""
    params = {"part": "contentDetails", "id": channel_id, "key": API_KEY}
    data = safe_get(CHANNELS_URL, params)
    items = data.get("items", [])
    if not items: 
        return None
    return items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")


def get_recent_video_ids(uploads_playlist_id: str, max_results: int) -> List[str]:
    """최근 영상 ID 목록 조회"""
    video_ids, page_token = [], None
    while len(video_ids) < max_results:
        params = {"part": "contentDetails", "playlistId": uploads_playlist_id,
                  "maxResults": min(50, max_results - len(video_ids)), "key": API_KEY}
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


def get_video_stats(video_ids: List[str]):
    """영상 통계 조회"""
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
    """영상의 모든 댓글 텍스트 수집"""
    texts, fetched, page_token = [], 0, None
    while True:
        params = {"part": "snippet,replies", "videoId": video_id, "maxResults": 100,
                  "textFormat": "plainText", "key": API_KEY}
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


def fetch_comments_structured_for_video(
    video_id: str,
    include_replies: bool = False,
    max_total: int = 500
) -> list[dict]:
    """구조화된 댓글 데이터 수집"""
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


def get_recent_video_stats(channel_id: str, num_videos: int = 5):
    """채널의 최신 N개 영상 통계를 리스트로 반환"""
    from models.youtube_models import VideoStatsOut
    
    try:
        playlist_id = get_uploads_playlist_id(channel_id)
        if not playlist_id:
            return []

        video_ids = get_recent_video_ids(playlist_id, max_results=num_videos)
        if not video_ids:
            return []

        stats = get_video_stats(video_ids)
        return stats
    
    except Exception as e:
        print(f"[Error] get_recent_video_stats 실패 (Channel: {channel_id}): {e}")
        return []


def get_latest_video_info(channel_id: str) -> Optional[Dict[str, str]]:
    """채널의 가장 최근 영상 1개의 video_id와 제목 반환"""
    up = get_uploads_playlist_id(channel_id)
    if not up:
        return None

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

    vinfo = safe_get(VIDEOS_URL, {"part": "snippet", "id": vid, "key": API_KEY})
    title = None
    if vinfo.get("items"):
        title = (vinfo["items"][0].get("snippet") or {}).get("title")

    return {"video_id": vid, "video_title": title}


def _fetch_video_snippets(video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """영상 스니펫 정보 조회 (title/description/tags/thumbnail)"""
    out: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        data = safe_get(VIDEOS_URL, {"part": "snippet", "id": ",".join(batch), "key": API_KEY})
        for item in data.get("items", []):
            vid = item.get("id")
            sn = item.get("snippet", {}) or {}
            thumbs = sn.get("thumbnails", {}) or {}
            thumb = (thumbs.get("high") or thumbs.get("default") or {}).get("url", "")
            out[vid] = {
                "title": sn.get("title", ""),
                "description": sn.get("description", ""),
                "tags": ", ".join(sn.get("tags", []) or []),
                "thumbnail_url": thumb,
            }
        sleep_short()
    return out


def _fetch_transcript_text(video_id: str) -> str:
    """영상 자막 텍스트 조회"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        tr = YouTubeTranscriptApi.get_transcript(video_id, languages=["ko", "en"])
        return " ".join(seg["text"] for seg in tr)
    except Exception:
        return ""


def fetch_top_comments_for_video(
    video_id: str,
    top_n: int = 10,
    max_scan: int = 300
) -> List[Dict[str, Any]]:
    """좋아요 수 기준 상위 N개 댓글 반환"""
    collected: List[Dict[str, Any]] = []
    scanned = 0
    page_token = None
    while True and scanned < max_scan:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": 100,
            "textFormat": "plainText",
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        data = safe_get(COMMENT_THREADS_URL, params)
        for thread in data.get("items", []):
            sn = (thread.get("snippet", {}) or {}).get("topLevelComment", {}) or {}
            top_sn = sn.get("snippet", {}) or {}
            collected.append({
                "comment_id": (thread.get("id") or ""),
                "text": top_sn.get("textDisplay"),
                "like_count": int(top_sn.get("likeCount") or 0),
                "author": top_sn.get("authorDisplayName"),
                "published_at": top_sn.get("publishedAt"),
            })
            scanned += 1
            if scanned >= max_scan:
                break
        if scanned >= max_scan:
            break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        sleep_short()

    collected.sort(key=lambda x: x.get("like_count", 0), reverse=True)
    return collected[:top_n]




