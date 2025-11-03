from fastapi import APIRouter, HTTPException, Query, Depends
from sqlmodel import Session, select, func 
from db.db import get_session, Influencer
from models.youtube_models import (
    SearchReq, KRPopularReq, VideoStatsReq, CommentsSummaryReq,
    ChannelDetails, VideoStatsOut, CommentsSummaryOut, HomeYoutuberCard, ChannelWithMetrics,LatestCommentsAnalyzeReq, LatestCommentsAnalyzeRes
)
from utils.youtube_utils import *
from youtube_transcript_api import YouTubeTranscriptApi
from utils.brand_fit import hybrid_brand_fit
from models.youtube_models import BrandAnalysisReq, BrandAnalysisOut

# 라우터 생성
youtube_router = APIRouter(tags=["YouTube API"])

# --------------------------
# 서버 헬스 체크
# --------------------------
@youtube_router.get("/health")
def health():
    """서버 정상 동작 여부 확인용"""
    return {"ok": True}

# 홈 화면 유튜버 리스트 (Get) - DB에서 조회
@youtube_router.get("/home-list", response_model=list[HomeYoutuberCard])
def get_home_youtuber_list(session: Session = Depends(get_session)): # DB 세션 주입
    """
    - (DB) 홈 화면에 노출할 유튜버 리스트 50명을 무작위로 반환
    """

    # 1. DB에서 Influencer 테이블을 랜덤으로 50명 조회
    statement = select(Influencer).order_by(func.random()).limit(50)
    influencers = session.exec(statement).all()

    # 2. DB 결과(Influencer)를 응답 모델(HomeYoutuberCard)로 변환
    result_cards = []
    for inf in influencers:
        card = HomeYoutuberCard(
            channel_id=inf.channel_id,
            channel_title=inf.title,
            subscriber_count=inf.subscriber_count,
            thumbnail_url=inf.thumbnail_url,
            category=inf.category or "미분류", # DB에 없으면 기본값
            engagement_rate=inf.engagement_rate,
            estimated_price=inf.estimated_price or "가격 문의" # DB에 없으면 기본값
        )
        result_cards.append(card)
    
    return result_cards

# --------------------------
# 키워드로 유튜버 검색 (카테고리 검색)
# --------------------------
@youtube_router.post("/youtubers/search", response_model=list[ChannelWithMetrics])
def search_youtubers(req: SearchReq):
    """
    - 키워드(예: '건강', '뷰티')로 유튜브 채널 검색
    - 채널 정보(썸네일, 구독자 수 등) + ROI + 참여율 반환
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

    details = fetch_channel_details(ids, source_tag=f"search:{req.keyword}")
    # ROI(임시), 참여율 계산 후 반환
    return attach_metrics_to_channels(details)


# --------------------------
# 한국 인기 유튜버 목록 (chart=mostPopular)
# --------------------------
@youtube_router.post("/youtubers/kr-popular", response_model=list[ChannelWithMetrics])
def kr_popular(req: KRPopularReq):
    """
    - 한국 지역에서 인기 영상 기반으로 채널 목록 추출
    - ROI(임시), 참여율 포함하여 반환
    - 구독자 수 100만 이상 채널만 필터링
    """
    # 1 인기 영상에서 채널 ID 수집
    ids = collect_channels_from_most_popular(region_code=req.region, pages=req.pages)
    if not ids:
        return []

    # 2 채널 상세정보 조회
    details = fetch_channel_details(ids, source_tag=f"kr-popular:{req.region}")

    # 3 구독자 수 기준 정렬
    details.sort(key=lambda r: (r.subscriber_count or 0), reverse=True)

    # 4 100만 이상 구독자 필터링
    min_subs = 1_000_000
    large_channels = [
        ch for ch in details
        if ch.subscriber_count and ch.subscriber_count >= min_subs and is_personnal_channel(ch)]

    # 5 ROI(임시) 및 참여율 계산 후 반환
    result = attach_metrics_to_channels(large_channels)

    # 6 top_n 제한
    return result[:req.top_n]


# --------------------------
# 채널의 최신 영상 통계 조회
# --------------------------
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


# --------------------------
# 댓글 수집 후 핵심 키워드 / 감성분석
# --------------------------
@youtube_router.post("/comments/summary", response_model=CommentsSummaryOut)
def comments_summary(req: CommentsSummaryReq):
    """
    - 채널/영상의 댓글 수집
    - 키워드 추출 + (옵션) 감성분석 요약 포함
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
        return CommentsSummaryOut(
            keywords=[], sentiment=None,
            counts={"videos_scanned": 0, "comments_used": 0}
        )

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
        return CommentsSummaryOut(
            keywords=[], sentiment=None,
            counts={"videos_scanned": len(video_pool), "comments_used": 0}
        )

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


@youtube_router.post("/comments/analyze-latest", response_model=LatestCommentsAnalyzeRes)
def analyze_latest_video_comments(req: LatestCommentsAnalyzeReq):
    """
    채널ID를 받아 해당 채널의 '가장 최근 영상' 1개의 댓글을:
    1) 수집 → 2) CSV 저장(옵션) → 3) 핵심 키워드 추출 까지 수행
    """
    # 1) 최신 영상 조회
    v = get_latest_video_info(req.channel_id)
    if not v:
        raise HTTPException(status_code=404, detail="해당 채널에서 최신 영상을 찾지 못했습니다.")
    video_id = v["video_id"]
    video_title = v.get("video_title")

    # 2) 댓글 수집 (구조화)
    rows = fetch_comments_structured_for_video(
        video_id=video_id,
        include_replies=req.include_replies,
        max_total=req.max_comments
    )

    # 수집 텍스트만 추출
    texts = [r.get("text") or "" for r in rows]

    # 3) 키워드 분석
    keywords = analyze_comments_keywords(texts, top_k=40)

    # 4) CSV 저장 (옵션)
    csv_path = None
    if req.save_csv:
        base = f"comments_{req.channel_id}_{video_id}"
        csv_path = save_comments_to_csv(rows, req.out_dir, base)

    return LatestCommentsAnalyzeRes(
        video_id=video_id,
        video_title=video_title,
        comments_used=len(texts),
        csv_path=csv_path,
        keywords=keywords
    )




@youtube_router.post("/brand-analysis", response_model=BrandAnalysisOut)
def brand_analysis(req: BrandAnalysisReq):
    """
    TF-IDF + 규칙 기반 + OpenAI 분석 하이브리드 브랜드 적합도 평가
    """
    # 1. 영상 정보
    data = safe_get(VIDEOS_URL, {"part": "snippet", "id": req.video_id, "key": API_KEY})
    item = (data.get("items") or [{}])[0]
    snippet = item.get("snippet", {}) or {}
    title = snippet.get("title", "")
    desc = snippet.get("description", "")
    tags = snippet.get("tags", [])

    # 2. 자막
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(req.video_id, languages=["ko", "en"])
        transcript = " ".join([seg["text"] for seg in transcript_list])
    except Exception:
        transcript = ""

    # 3. 분석
    result = hybrid_brand_fit(
        title=title,
        desc=desc,
        transcript=transcript,
        tags=tags,
        brand_keywords=req.brand_keywords,
        knu_tone=None,
        use_llm=req.use_llm
    )

    return BrandAnalysisOut(
        video_id=req.video_id,
        title=title,
        description=desc,
        brand_fit_score=result["brand_fit_score"],
        components=result["components"],
        top_keywords=result["top_keywords"],
        matched_tags=result["matched_tags"],
        llm_reason=result["llm_reason"]
    )