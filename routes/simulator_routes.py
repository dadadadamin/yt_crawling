from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from db.db import get_session, Influencer
from models.roi_models import (
    SimulatorRequest, SimulatorResponse, BrandImageScore,
    SentimentScore, ROIEstimate, TotalScore, WeightConfig,
    calculate_total_score, assign_grade, generate_recommendation,
    calculate_roi_score_from_engagement,
    BrandCompatibilityRequest, CompareWeightsRequest  # 추가
)
from utils.youtube_utils import (
    get_uploads_playlist_id,
    get_recent_video_ids,
    get_video_stats,
    fetch_all_comments_for_video,
    fetch_channel_details
)
from utils.sentiment_analysis import analyze_comments_batch_kobert
from utils.brand_analysis import analyze_brand_compatibility  # 추가
import time
from typing import Optional, List

simulator_router = APIRouter(tags=["ROI Simulator"])

# ============================================
# 1. 브랜드 이미지 적합도 분석 (CLIP 기반)
# ============================================

def analyze_brand_image_compatibility(
    channel_id: str,
    brand_name: str,
    brand_description: str,
    brand_tone: str,
    brand_category: str,
    brand_image_url: Optional[str] = None,
    brand_image_base64: Optional[str] = None,
    session: Session = None
) -> BrandImageScore:
    """
    브랜드-유튜버 이미지 적합도 분석 (CLIP + Sentence-BERT)
    """
    try:
        # DB에서 채널 정보 조회
        influencer = session.get(Influencer, channel_id) if session else None
        if not influencer:
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")
        
        # 최신 영상 정보 가져오기
        uploads_id = get_uploads_playlist_id(channel_id)
        if not uploads_id:
            raise HTTPException(status_code=404, detail="채널 영상을 찾을 수 없습니다")
        
        video_ids = get_recent_video_ids(uploads_id, max_results=5)
        video_stats = get_video_stats(video_ids)
        
        # 썸네일 URL 및 제목 추출
        channel_thumbnails = []
        video_titles = []
        
        for video in video_stats:
            # VideoStatsOut 객체에서 속성 추출
            if hasattr(video, 'video_title') and video.video_title:
                video_titles.append(video.video_title)
        
        # 영상 썸네일은 별도 API 호출이 필요할 수 있음 (간소화를 위해 채널 썸네일 사용)
        if influencer.thumbnail_url:
            channel_thumbnails = [influencer.thumbnail_url]
        
        # 브랜드 적합도 분석 실행
        result = analyze_brand_compatibility(
            # 브랜드 정보
            brand_name=brand_name,
            brand_description=brand_description,
            brand_tone=brand_tone,
            brand_category=brand_category,
            # 채널 정보
            channel_id=channel_id,
            channel_description=influencer.description or "",
            channel_category=influencer.category,
            channel_thumbnails=channel_thumbnails,
            video_titles=video_titles,
            # 브랜드 이미지 (선택)
            brand_image_url=brand_image_url,
            brand_image_base64=brand_image_base64
        )
        
        return BrandImageScore(
            channel_id=result["channel_id"],
            brand_name=result["brand_name"],
            overall_score=result["overall_score"],
            image_similarity=result["image_similarity"],
            text_similarity=result["text_similarity"],
            tone_match=result["tone_match"],
            category_match=result["category_match"],
            detailed_analysis=result["detailed_analysis"],
            analysis_method="clip_sbert"
        )
    
    except Exception as e:
        print(f"[Error] 브랜드 분석 실패: {e}")
        # 에러 시 기본값 반환
        return BrandImageScore(
            channel_id=channel_id,
            brand_name=brand_name,
            overall_score=50.0,
            image_similarity=50.0,
            text_similarity=50.0,
            tone_match=50.0,
            category_match=50.0,
            detailed_analysis={},
            analysis_method="error_fallback"
        )


# ============================================
# 2. 감성분석 실행
# ============================================

def perform_sentiment_analysis(
    channel_id: str,
    num_videos: int = 3,
    max_comments_per_video: int = 200
) -> SentimentScore:
    """
    KoBERT 기반 유튜버 댓글 감성분석
    """
    # 1. 업로드 플레이리스트 ID 가져오기
    uploads_id = get_uploads_playlist_id(channel_id)
    if not uploads_id:
        raise HTTPException(status_code=404, detail="채널의 업로드 플레이리스트를 찾을 수 없습니다")
    
    # 2. 최신 영상 ID 가져오기
    video_ids = get_recent_video_ids(uploads_id, max_results=num_videos)
    if not video_ids:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다")
    
    # 3. 각 영상의 댓글 수집
    all_comments = []
    videos_analyzed = 0
    
    for video_id in video_ids:
        try:
            comments = fetch_all_comments_for_video(
                video_id,
                include_replies=False,
                max_total=max_comments_per_video
            )
            all_comments.extend(comments)
            videos_analyzed += 1
        except Exception as e:
            print(f"[Warning] 영상 {video_id} 댓글 수집 실패: {e}")
            continue
    
    if not all_comments:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")
    
    # 4. KoBERT 감성분석 실행
    result = analyze_comments_batch_kobert(all_comments)
    
    return SentimentScore(
        channel_id=channel_id,
        positive_ratio=result["positive_ratio"],
        negative_ratio=result["negative_ratio"],
        neutral_ratio=result["neutral_ratio"],
        sentiment_score=result["sentiment_score"],
        total_comments=result["total_comments"],
        videos_analyzed=videos_analyzed
    )


# ============================================
# 3. ROI 예상값 계산
# ============================================

def estimate_roi(
    channel_id: str,
    session: Session
) -> ROIEstimate:
    """
    참여율 기반 ROI 예상값 계산
    """
    # DB에서 채널 정보 조회
    influencer = session.get(Influencer, channel_id)
    if not influencer:
        raise HTTPException(status_code=404, detail="채널 정보를 찾을 수 없습니다")
    
    if not influencer.engagement_rate or not influencer.subscriber_count:
        raise HTTPException(
            status_code=400,
            detail="참여율 또는 구독자 수 정보가 없습니다"
        )
    
    # 예상 비용 (estimated_price를 숫자로 변환)
    price_str = influencer.estimated_price or "가격 문의"
    cost_map = {
        "100만원": 1000000,
        "200만원": 2000000,
        "300만원": 3000000,
        "500만원": 5000000,
        "가격문의": 5000000,
        "가격 문의": 5000000
    }
    estimated_cost = cost_map.get(price_str, 2000000)

    # ROI 점수 계산
    roi_data = calculate_roi_score_from_engagement(
        engagement_rate=influencer.engagement_rate,
        subscriber_count=influencer.subscriber_count,
        estimated_cost=estimated_cost
    )

    return ROIEstimate(
        channel_id=channel_id,
        **roi_data
    )


# ============================================
# 4. 브랜드 적합도 분석 단독 API
# ============================================

@simulator_router.post("/brand-compatibility", response_model=BrandImageScore)
def run_brand_compatibility_analysis(
    req: BrandCompatibilityRequest,
    session: Session = Depends(get_session)
):
    """
    브랜드-채널 이미지 적합도 분석 (단독 실행)
    
    - 제품 이미지와 채널 썸네일 비교 (CLIP)
    - 브랜드 설명과 채널 콘텐츠 유사도 (Sentence-BERT)
    - 톤앤매너 매칭도
    - 카테고리 매칭도
    """
    return analyze_brand_image_compatibility(
        channel_id=req.channel_id,
        brand_name=req.brand_name,
        brand_description=req.brand_description,
        brand_tone=req.brand_tone,
        brand_category=req.brand_category,
        brand_image_url=req.brand_image_url,
        brand_image_base64=req.brand_image_base64,
        session=session
    )


# ============================================
# 5. 감성분석 단독 API
# ============================================

@simulator_router.get("/sentiment/{channel_id}", response_model=SentimentScore)
def run_sentiment_analysis(
    channel_id: str,
    num_videos: int = 3,
    max_comments_per_video: int = 200
):
    """
    채널 댓글 감성분석 (단독 실행)
    
    - KoBERT 기반 감성 분류
    - 긍정/부정/중립 비율
    - 감성 점수 (0-100)
    """
    return perform_sentiment_analysis(
        channel_id=channel_id,
        num_videos=num_videos,
        max_comments_per_video=max_comments_per_video
    )


# ============================================
# 6. 시뮬레이터 메인 API
# ============================================

@simulator_router.post("/simulate", response_model=SimulatorResponse)
def run_simulator(
    req: SimulatorRequest,
    session: Session = Depends(get_session)
):
    """
    유튜버 마케팅 ROI 시뮬레이터 실행

    1. 브랜드 이미지 적합도 분석 (CLIP + SBERT)
    2. 댓글 감성분석 (KoBERT)
    3. ROI 예상값 계산
    4. 가중치 적용 최종 점수 산출
    """
    start_time = time.time()
    errors = []

    # 채널 정보 조회
    influencer = session.get(Influencer, req.channel_id)
    if not influencer:
        raise HTTPException(status_code=404, detail=f"채널 {req.channel_id}를 찾을 수 없습니다")

    # 1. 브랜드 이미지 적합도
    brand_image = None
    try:
        brand_image = analyze_brand_image_compatibility(
            channel_id=req.channel_id,
            brand_name=req.brand_name,
            brand_description=req.brand_description,
            brand_tone=req.brand_tone,
            brand_category=req.brand_category,
            brand_image_url=req.brand_image_url,
            brand_image_base64=req.brand_image_base64,
            session=session
        )
    except Exception as e:
        errors.append(f"브랜드 이미지 분석 실패: {str(e)}")
        brand_image = BrandImageScore(
            channel_id=req.channel_id,
            brand_name=req.brand_name,
            overall_score=50.0,
            image_similarity=50.0,
            text_similarity=50.0,
            tone_match=50.0,
            category_match=50.0,
            detailed_analysis={},
            analysis_method="error"
        )
    
    # 2. 감성분석
    sentiment = None
    try:
        sentiment = perform_sentiment_analysis(
            channel_id=req.channel_id,
            num_videos=req.num_videos,
            max_comments_per_video=req.max_comments_per_video
        )
    except Exception as e:
        errors.append(f"감성분석 실패: {str(e)}")
        sentiment = SentimentScore(
            channel_id=req.channel_id,
            positive_ratio=50.0,
            negative_ratio=25.0,
            neutral_ratio=25.0,
            sentiment_score=50.0,
            total_comments=0,
            videos_analyzed=0
        )

    # 3. ROI 예상
    roi_estimate = None
    try:
        roi_estimate = estimate_roi(
            channel_id=req.channel_id,
            session=session
        )
    except Exception as e:
        errors.append(f"ROI 계산 실패: {str(e)}")
        roi_estimate = ROIEstimate(
            channel_id=req.channel_id,
            estimated_views=0,
            estimated_engagement=0,
            cost_estimate=2000000,
            roi_score=50.0,
            engagement_rate=0.0
        )

    # 4. 최종 점수 계산 (브랜드 이미지의 overall_score 사용)
    total_score_value = calculate_total_score(
        brand_score=brand_image.overall_score,  # 변경
        sentiment_score=sentiment.sentiment_score,
        roi_score=roi_estimate.roi_score,
        weights=req.weights
    )

    grade = assign_grade(total_score_value)
    recommendation = generate_recommendation(
        total_score_value,
        {
            "brand_image": brand_image.overall_score,  # 변경
            "sentiment": sentiment.sentiment_score,
            "roi": roi_estimate.roi_score
        }
    )

    total_score = TotalScore(
        channel_id=req.channel_id,
        channel_title=influencer.title,
        thumbnail_url=influencer.thumbnail_url,
        brand_image_score=brand_image.overall_score,  # 변경
        sentiment_score=sentiment.sentiment_score,
        roi_score=roi_estimate.roi_score,
        weights=req.weights,
        total_score=total_score_value,
        subscriber_count=influencer.subscriber_count,
        engagement_rate=influencer.engagement_rate,
        estimated_cost=roi_estimate.cost_estimate,
        grade=grade,
        recommendation=recommendation
    )

    processing_time = time.time() - start_time

    return SimulatorResponse(
        channel_id=req.channel_id,
        channel_title=influencer.title,
        brand_image=brand_image,
        sentiment=sentiment,
        roi_estimate=roi_estimate,
        total_score=total_score,
        processing_time_seconds=round(processing_time, 2),
        errors=errors
    )


# ============================================
# 7. 가중치 비교 API
# ============================================

@simulator_router.post("/compare-weights")
def compare_weights(
    request: CompareWeightsRequest,
    session: Session = Depends(get_session)
):
    """
    여러 가중치 설정으로 점수 비교

    예: [
        {"brand_image_weight": 0.5, "sentiment_weight": 0.3, "roi_weight": 0.2},
        {"brand_image_weight": 0.3, "sentiment_weight": 0.3, "roi_weight": 0.4},
        {"brand_image_weight": 0.2, "sentiment_weight": 0.5, "roi_weight": 0.3}
    ]
    """

    # 기본 분석 실행 (1회만)
    base_req = SimulatorRequest(
        channel_id=request.channel_id,
        brand_name=request.brand_name,
        brand_description=request.brand_description,
        brand_tone=request.brand_tone,
        brand_category=request.brand_category,
        brand_image_url=request.brand_image_url,
        weights=request.weight_configs[0]  # 첫 번째 설정으로 분석
    )

    base_result = run_simulator(base_req, session)

    # 각 가중치 설정별 점수 계산
    comparisons = []
    for weights in request.weight_configs:
        total = calculate_total_score(
            brand_score=base_result.brand_image.overall_score,  # 변경
            sentiment_score=base_result.sentiment.sentiment_score,
            roi_score=base_result.roi_estimate.roi_score,
            weights=weights
        )
        
        comparisons.append({
            "weights": weights.model_dump(),
            "total_score": total,
            "grade": assign_grade(total),
            "recommendation": generate_recommendation(total, {
                "brand_image": base_result.brand_image.overall_score,  # 변경
                "sentiment": base_result.sentiment.sentiment_score,
                "roi": base_result.roi_estimate.roi_score
            })
        })

    return {
        "channel_id": request.channel_id,
        "channel_title": base_result.channel_title,
        "base_scores": {
            "brand_image": base_result.brand_image.overall_score,
            "sentiment": base_result.sentiment.sentiment_score,
            "roi": base_result.roi_estimate.roi_score
        },
        "comparisons": comparisons
    }