from pydantic import BaseModel, Field
from typing import Optional, Dict, List

# ============================================
# 요청 모델
# ============================================

class BrandCompatibilityRequest(BaseModel):
    """브랜드 적합도 분석 요청"""
    channel_id: str = Field(..., description="채널 ID")
    brand_name: str = Field(..., description="브랜드/제품 이름")
    brand_description: str = Field(..., description="제품 설명")
    brand_tone: str = Field(..., description="브랜드 톤앤매너", example="친근하고 밝은 분위기")
    brand_category: str = Field(..., description="브랜드 카테고리", example="뷰티")
    brand_image_url: Optional[str] = Field(None, description="제품 이미지 URL")
    brand_image_base64: Optional[str] = Field(None, description="제품 이미지 Base64")


class WeightConfig(BaseModel):
    """가중치 설정"""
    brand_image_weight: float = Field(0.4, ge=0, le=1, description="브랜드 이미지 가중치")
    sentiment_weight: float = Field(0.3, ge=0, le=1, description="감성분석 가중치")
    roi_weight: float = Field(0.3, ge=0, le=1, description="ROI 가중치")


class SimulatorRequest(BaseModel):
    """시뮬레이터 실행 요청"""
    channel_id: str = Field(..., description="채널 ID")
    brand_name: str = Field(..., description="브랜드 이름")
    brand_description: str = Field(..., description="제품 설명")
    brand_tone: str = Field(..., description="브랜드 톤앤매너")
    brand_category: str = Field(..., description="브랜드 카테고리")
    brand_image_url: Optional[str] = Field(None, description="브랜드 이미지 URL")
    brand_image_base64: Optional[str] = Field(None, description="브랜드 이미지 Base64")
    
    num_videos: int = Field(3, ge=1, le=10, description="분석할 영상 수")
    max_comments_per_video: int = Field(200, ge=50, le=500, description="영상당 댓글 수")
    weights: WeightConfig = Field(default_factory=WeightConfig, description="가중치 설정")


class CompareWeightsRequest(BaseModel):
    """가중치 비교 요청"""
    channel_id: str = Field(..., description="채널 ID")
    brand_name: str = Field(..., description="브랜드 이름")
    brand_description: str = Field(..., description="제품 설명")
    brand_tone: str = Field(..., description="브랜드 톤앤매너")
    brand_category: str = Field(..., description="브랜드 카테고리")
    weight_configs: List[WeightConfig] = Field(..., description="비교할 가중치 설정 리스트")
    brand_image_url: Optional[str] = Field(None, description="브랜드 이미지 URL")


# ============================================
# 응답 모델
# ============================================

class BrandImageScore(BaseModel):
    """브랜드 이미지 적합도 결과"""
    channel_id: str
    brand_name: str
    overall_score: float = Field(..., description="종합 적합도 (0-100)")
    image_similarity: float = Field(..., description="이미지 유사도 (0-100)")
    text_similarity: float = Field(..., description="텍스트 유사도 (0-100)")
    tone_match: float = Field(..., description="톤앤매너 매칭 (0-100)")
    category_match: float = Field(..., description="카테고리 매칭 (0-100)")
    detailed_analysis: Dict = Field(default_factory=dict, description="상세 분석")
    analysis_method: str = Field(default="clip_sbert", description="분석 방법")


class SentimentScore(BaseModel):
    """감성분석 결과"""
    channel_id: str
    positive_ratio: float = Field(..., description="긍정 비율 (%)")
    negative_ratio: float = Field(..., description="부정 비율 (%)")
    neutral_ratio: float = Field(..., description="중립 비율 (%)")
    sentiment_score: float = Field(..., description="감성 점수 (0-100)")
    total_comments: int = Field(..., description="분석된 댓글 수")
    videos_analyzed: int = Field(..., description="분석된 영상 수")


class ROIEstimate(BaseModel):
    """ROI 예상 결과"""
    channel_id: str
    estimated_views: int = Field(..., description="예상 조회수")
    estimated_engagement: int = Field(..., description="예상 참여 수")
    cost_estimate: int = Field(..., description="예상 비용 (원)")
    roi_score: float = Field(..., description="ROI 점수 (0-100)")
    engagement_rate: float = Field(..., description="참여율 (%)")


class TotalScore(BaseModel):
    """최종 종합 점수"""
    channel_id: str
    channel_title: str
    thumbnail_url: Optional[str]
    brand_image_score: float
    sentiment_score: float
    roi_score: float
    weights: WeightConfig
    total_score: float = Field(..., description="최종 점수 (0-100)")
    subscriber_count: Optional[int]
    engagement_rate: Optional[float]
    estimated_cost: int
    grade: str = Field(..., description="등급 (S/A/B/C/D)")
    recommendation: str = Field(..., description="추천 의견")


class SimulatorResponse(BaseModel):
    """시뮬레이터 실행 결과"""
    channel_id: str
    channel_title: str
    brand_image: BrandImageScore
    sentiment: SentimentScore
    roi_estimate: ROIEstimate
    total_score: TotalScore
    processing_time_seconds: float
    errors: List[str] = Field(default_factory=list)


# ============================================
# 유틸리티 함수
# ============================================

def calculate_total_score(
    brand_score: float,
    sentiment_score: float,
    roi_score: float,
    weights: WeightConfig
) -> float:
    """가중치 적용 최종 점수 계산"""
    total = (
        brand_score * weights.brand_image_weight +
        sentiment_score * weights.sentiment_weight +
        roi_score * weights.roi_weight
    )
    return round(total, 2)


def assign_grade(score: float) -> str:
    """점수에 따른 등급 부여"""
    if score >= 90:
        return "S"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    else:
        return "D"


def generate_recommendation(score: float, breakdown: Dict[str, float]) -> str:
    """점수 기반 추천 메시지 생성"""
    if score >= 90:
        return "🌟 최고 수준의 적합도! 적극 추천합니다."
    elif score >= 80:
        return "✅ 우수한 적합도! 협찬 진행을 권장합니다."
    elif score >= 70:
        return "👍 양호한 적합도. 협찬 고려 가능합니다."
    elif score >= 60:
        return "⚠️ 보통 수준. 신중한 검토가 필요합니다."
    else:
        # 가장 낮은 점수 찾기
        min_key = min(breakdown, key=breakdown.get)
        return f"❌ 적합도 낮음. 특히 {min_key} 개선이 필요합니다."


def calculate_roi_score_from_engagement(
    engagement_rate: float,
    subscriber_count: int,
    estimated_cost: int
) -> Dict[str, any]:
    """참여율 기반 ROI 점수 계산"""
    # 예상 조회수 (구독자의 10-30%)
    estimated_views = int(subscriber_count * 0.2)
    
    # 예상 참여 수
    estimated_engagement = int(estimated_views * (engagement_rate / 100))
    
    # ROI 점수 계산 (참여당 비용 기준)
    if estimated_engagement > 0:
        cost_per_engagement = estimated_cost / estimated_engagement
        
        # 참여당 비용이 낮을수록 높은 점수
        # 1000원 이하 = 90점, 5000원 = 50점, 10000원 이상 = 10점
        if cost_per_engagement <= 1000:
            roi_score = 90 + (1000 - cost_per_engagement) / 100
        elif cost_per_engagement <= 5000:
            roi_score = 50 + (5000 - cost_per_engagement) / 100
        else:
            roi_score = max(10, 50 - (cost_per_engagement - 5000) / 200)
    else:
        roi_score = 0
    
    return {
        "estimated_views": estimated_views,
        "estimated_engagement": estimated_engagement,
        "cost_estimate": estimated_cost,
        "roi_score": round(min(100, max(0, roi_score)), 2),
        "engagement_rate": engagement_rate
    }