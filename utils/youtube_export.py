#YouTube 데이터 CSV 내보내기 관련 유틸리티 -데이터 제출용
import os
import csv
from typing import List, Dict, Any
from fastapi import HTTPException

from utils.youtube_api import (
    API_KEY,
    VIDEOS_URL,
    safe_get,
    sleep_short,
    fetch_channel_details,
    get_uploads_playlist_id,
    get_recent_video_ids,
    get_video_stats,
    get_recent_video_stats,
    _fetch_video_snippets,
    _fetch_transcript_text,
    fetch_top_comments_for_video,
)
from utils.youtube_analysis import (
    calculate_engagement_rate_from_stats,
    is_personnal_channel,
)
from utils.youtube_api import search_channels_by_keyword


def save_comments_to_csv(rows: List[Dict[str, Any]], out_dir: str, base_name: str) -> str:
    """댓글 데이터를 CSV로 저장"""
    os.makedirs(out_dir, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in base_name)[:60]
    path = os.path.join(out_dir, f"{safe_name}.csv")

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


def export_influencer_metadata_csv(
    channel_ids: List[str],
    out_path: str,
    max_videos_for_avg: int = 5
) -> str:
    """인플루언서 메타데이터 CSV 생성"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    details = fetch_channel_details(channel_ids, source_tag="export:meta")

    fieldnames = [
        "channel_id", "title",
        "subscriber_count", "view_count", "video_count",
        "avg_like_count", "avg_comment_count",
        "engagement_rate", "thumbnail_url"
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ch in details:
            stats = get_recent_video_stats(ch.channel_id, num_videos=max_videos_for_avg)
            if stats:
                avg_like = round(sum((s.like_count or 0) for s in stats) / len(stats), 2)
                avg_comment = round(sum((s.comment_count or 0) for s in stats) / len(stats), 2)
            else:
                avg_like = 0.0
                avg_comment = 0.0
            eng_rate = calculate_engagement_rate_from_stats(stats, ch.subscriber_count or 0)

            writer.writerow({
                "channel_id": ch.channel_id,
                "title": ch.title,
                "subscriber_count": ch.subscriber_count,
                "view_count": ch.view_count,
                "video_count": ch.video_count,
                "avg_like_count": avg_like,
                "avg_comment_count": avg_comment,
                "engagement_rate": eng_rate,
                "thumbnail_url": ch.thumbnail_url,
            })
    return out_path


def export_video_info_csv(
    video_ids: List[str],
    out_path: str
) -> str:
    """영상 정보 CSV 생성"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        data = safe_get(VIDEOS_URL, {"part": "snippet", "id": ",".join(batch), "key": API_KEY})
        for item in data.get("items", []):
            vid = item.get("id")
            sn = item.get("snippet", {}) or {}
            title = sn.get("title", "")
            desc = sn.get("description", "")
            tags = sn.get("tags", []) or []
            thumbs = sn.get("thumbnails", {}) or {}
            thumb = (thumbs.get("high") or thumbs.get("default") or {}).get("url", "")

            transcript_text = ""
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                transcript_list = YouTubeTranscriptApi.get_transcript(vid, languages=["ko", "en"])
                transcript_text = " ".join(seg["text"] for seg in transcript_list)
            except Exception:
                transcript_text = ""

            rows.append({
                "video_id": vid,
                "title": title,
                "description": desc,
                "transcript": transcript_text,
                "tags": ", ".join(tags),
                "thumbnail_url": thumb
            })
        sleep_short()

    fieldnames = ["video_id", "title", "description", "transcript", "tags", "thumbnail_url"]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return out_path


def _pick_top_channels_for_category(category_keyword: str, target_count: int = 10) -> List[str]:
    """카테고리별 상위 채널 선택"""
    candidates = search_channels_by_keyword(category_keyword, top_n=max(60, target_count * 6))
    if not candidates:
        return []

    details = fetch_channel_details(candidates, source_tag=f"category:{category_keyword}")
    picked: List[str] = []
    for ch in details:
        subs = ch.subscriber_count or 0
        if 100000 <= subs <= 1000000 and is_personnal_channel(ch):
            picked.append(ch.channel_id)
        if len(picked) >= target_count:
            break
    return picked


def export_category_influencers_csv(
    categories: List[str],
    out_path: str,
    recent_videos_for_sum: int = 20
) -> str:
    """카테고리별 인플루언서 CSV 생성"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    fieldnames = [
        "category", "channel_id", "title", "description",
        "subscriber_count", "channel_total_views",
        "recent_uploads_views_sum", "country", "thumbnail_url"
    ]

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for cat in list(dict.fromkeys(categories)):
            try:
                channel_ids = _pick_top_channels_for_category(cat, target_count=10)
                if not channel_ids:
                    continue
                infos = fetch_channel_details(channel_ids, source_tag=f"category:{cat}")

                for ch in infos:
                    uploads_id = get_uploads_playlist_id(ch.channel_id)
                    recent_ids = get_recent_video_ids(uploads_id, max_results=recent_videos_for_sum) if uploads_id else []
                    stats = get_video_stats(recent_ids) if recent_ids else []
                    recent_views_sum = int(sum((s.view_count or 0) for s in stats)) if stats else 0

                    writer.writerow({
                        "category": cat,
                        "channel_id": ch.channel_id,
                        "title": ch.title,
                        "description": ch.description,
                        "subscriber_count": ch.subscriber_count,
                        "channel_total_views": ch.view_count,
                        "recent_uploads_views_sum": recent_views_sum,
                        "country": ch.country,
                        "thumbnail_url": ch.thumbnail_url
                    })
            except Exception:
                continue

    return out_path


def export_channel_latest_videos_with_comments_csv(
    channel_id: str,
    out_path: str,
    num_videos: int = 3,
    top_comments: int = 10
) -> str:
    """채널 최근 영상 + 상위 댓글 CSV 생성"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    uploads = get_uploads_playlist_id(channel_id)
    if not uploads:
        raise HTTPException(status_code=404, detail="업로드 재생목록을 찾을 수 없습니다.")
    video_ids = get_recent_video_ids(uploads, max_results=num_videos)
    if not video_ids:
        raise HTTPException(status_code=404, detail="최근 영상을 찾을 수 없습니다.")

    snippets = _fetch_video_snippets(video_ids)

    fieldnames = [
        "video_id", "title", "description", "transcript", "tags", "thumbnail_url",
        "comment_rank", "comment_id", "comment_text", "comment_like_count",
        "comment_author", "comment_published_at"
    ]

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for vid in video_ids:
            meta = snippets.get(vid, {})
            transcript = _fetch_transcript_text(vid)
            top_comms = fetch_top_comments_for_video(vid, top_n=top_comments, max_scan=300)

            if not top_comms:
                writer.writerow({
                    "video_id": vid,
                    "title": meta.get("title", ""),
                    "description": meta.get("description", ""),
                    "transcript": transcript,
                    "tags": meta.get("tags", ""),
                    "thumbnail_url": meta.get("thumbnail_url", ""),
                    "comment_rank": None,
                    "comment_id": None,
                    "comment_text": None,
                    "comment_like_count": None,
                    "comment_author": None,
                    "comment_published_at": None,
                })
                continue

            for rank, c in enumerate(top_comms, start=1):
                writer.writerow({
                    "video_id": vid,
                    "title": meta.get("title", ""),
                    "description": meta.get("description", ""),
                    "transcript": transcript,
                    "tags": meta.get("tags", ""),
                    "thumbnail_url": meta.get("thumbnail_url", ""),
                    "comment_rank": rank,
                    "comment_id": c.get("comment_id"),
                    "comment_text": c.get("text"),
                    "comment_like_count": c.get("like_count"),
                    "comment_author": c.get("author"),
                    "comment_published_at": c.get("published_at"),
                })

    return out_path




