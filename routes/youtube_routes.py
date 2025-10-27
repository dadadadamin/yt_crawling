from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select, func 
from db import get_session, Influencer
from models.youtube_models import (
    SearchReq, KRPopularReq, VideoStatsReq, CommentsSummaryReq,
    ChannelDetails, VideoStatsOut, CommentsSummaryOut
)
from utils.youtube_utils import *

# 라우터 생성
youtube_router = APIRouter(tags=["YouTube API"])

# 서버 헬스 체크
@youtube_router.get("/health")
def health():
    """서버 정상 동작 여부 확인용"""
    return {"ok": True}

# 홈 화면 유튜버 리스 (Get) - DB에서 초고속 조회
@youtube_router.get("/home-list", response_model=list[HomeYoutuberCard])

#키워드로 유튜버 검색
@youtube_router.post("/youtubers/search", response_model=list[ChannelDetails])
def search_youtubers(req: SearchReq):
    """
    - 키워드(예: '건강', '뷰티')로 유튜브 채널 검색
    - 채널 정보(썸네일, 구독자 수 등) 반환
    """
    ids, page_token = [], None

    while len(ids) < req.top_n:
        params = {
            "part": "snippet",
            "type": "channel",
            "q": req.keyword,
            "maxResults": 50,
            "key": API_KEY,
            "order": "relevance",
            "regionCode": req.region,
            "relevanceLanguage": req.lang
        }
        if page_token:
            params["pageToken"] = page_token

        data = safe_get(SEARCH_URL, params)

        # 채널 ID만 추출
        for item in data.get("items", []):
            ch = item.get("id", {}).get("channelId")
            if ch and ch not in ids:
                ids.append(ch)
                if len(ids) >= req.top_n:
                    break

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        sleep_short()

    if not ids:
        return []

    return fetch_channel_details(ids, source_tag=f"search:{req.keyword}")


# 한국 인기 유튜버 목록 (chart=mostPopular)
@youtube_router.post("/youtubers/kr-popular", response_model=list[ChannelDetails])
def kr_popular(req: KRPopularReq):
    """
    - 한국 지역에서 인기 영상 기반으로 채널 목록 추출
    - 구독자 수 기준으로 상위 N 반환
    """
    ids = collect_channels_from_most_popular(region_code=req.region, pages=req.pages)
    if not ids:
        return []

    details = fetch_channel_details(ids, source_tag=f"kr-popular:{req.region}")
    details.sort(key=lambda r: (r.subscriber_count or 0), reverse=True)
    return details[:req.top_n]


# 채널의 최신 영상 통계 조회
@youtube_router.post("/videos/stats", response_model=list[VideoStatsOut])
def videos_stats(req: VideoStatsReq):
    """
    - 채널 ID 또는 영상 ID 기준으로
      영상 제목 / 조회수 / 좋아요 / 댓글 수 반환
    """
    all_rows: list[VideoStatsOut] = []

    # 직접 지정한 video_ids가 있으면 먼저 조회
    if req.video_ids:
        all_rows.extend(get_video_stats(req.video_ids))

    # 채널별 업로드 영상 정보 조회
    if req.channel_ids:
        ch_details = fetch_channel_details(req.channel_ids, source_tag="videos-stats")
        title_by_id = {c.channel_id: (c.title or None) for c in ch_details}

        for ch in req.channel_ids:
            up = get_uploads_playlist_id(ch)
            if not up:
                continue

            vids = get_recent_video_ids(up, max_results=req.max_videos_per_channel)
            stats = get_video_stats(vids)

            for r in stats:
                r.channel_id = ch
                r.channel_title = title_by_id.get(ch)

            all_rows.extend(stats)

    return all_rows


# 댓글 수집 후 핵심 키워드 / 감성분석
@youtube_router.post("/comments/summary", response_model=CommentsSummaryOut)
def comments_summary(req: CommentsSummaryReq):
    """
    - 채널/영상의 댓글 수집
    - TF-IDF 기반 핵심 키워드 추출
    - (옵션) 감성분석 요약 포함
    """
    video_pool = []

    # 영상 ID 직접 지정 or 채널로부터 추출
    if req.video_ids:
        video_pool.extend(req.video_ids)
    if req.channel_ids:
        for ch in req.channel_ids:
            up = get_uploads_playlist_id(ch)
            if up:
                vids = get_recent_video_ids(up, max_results=req.max_videos_per_channel)
                video_pool.extend(vids)

    video_pool = list(dict.fromkeys(video_pool))  # 중복 제거
    if not video_pool:
        return CommentsSummaryOut(keywords=[], sentiment=None, counts={"videos_scanned": 0, "comments_used": 0})

    # 댓글 수집
    texts: list[str] = []
    for vid in video_pool:
        try:
            texts.extend(fetch_all_comments_for_video(
                vid,
                include_replies=req.include_replies,
                max_total=req.max_comments_per_video
            ))
        except HTTPException:
            continue

    if not texts:
        return CommentsSummaryOut(keywords=[], sentiment=None, counts={"videos_scanned": len(video_pool), "comments_used": 0})

    # 키워드 & 감성분석
    keywords = extract_keywords_tfidf(texts, top_k=req.keyword_top_k)
    sentiment = None
    if req.sentiment == "basic":
        sentiment = basic_sentiment_summary(texts)

    return CommentsSummaryOut(
        keywords=keywords,
        sentiment=sentiment,
        counts={"videos_scanned": len(video_pool), "comments_used": len(texts)}
    )
