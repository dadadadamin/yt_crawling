from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class BrandImageScore(BaseModel):
    """브랜드-유튜버 이미지 적합도 점수"""
    channel_id: str
    brand_name: str
    similarity_score: float = Field(..., ge=0, le=100, description="이미지 유사도(0-100)")
    analysis_method: str = Field(default="clip", description="사용된 분석 방법")
    thumbnail_url: Optional[str] = None
    brand_image_url: Optional[str] = None

class SentimentScore(BaseModel):
    """감성분석 점수"""
    channel_id: str
    positive_ratio: float = Field(..., ge=0, le=100, description="긍정 비율 (%)")
    negative_ratio: float = Field(..., ge=0, le=100, description="부정 비율 (%)")
    neutral_ratio: float = Field(..., ge=0, le=100, description="중립 비율 (%)")
    sentiment_score: float = Field(..., ge=0, le=100, description="최종 감성 점수 (0-100)")
    total_comments: int = Field(..., description="분석된 댓글 수")
    videos_analyzed: int = Field(default=3, description="분석된 영상 수")

class ROIEstimate(BaseModel):
    """ROI 예상값"""
    channel_id: str
    estimated_views: int = Field(..., description="예상 조회수")
    estimated_engagement: int = Field(..., description="예상 참여수 (좋아요+댓글)")
    cost_estimate: int = Field(..., description="예상 비용 (원)")
    roi_score: float = Field(..., ge=0, le=100, description="ROI 점수 (0-100)")
    engagement_rate: float = Field(..., description="참여율 (%)")
    cpe: Optional[float] = Field(None, description="Cost Per Engagement")
    cpv: Optional[float] = Field(None, description="Cost Per View")

class WeightConfig(BaseModel):
    """가중치 설정"""
    brand_image_weight: float = Field(0.3, ge=0, le=1, description="브랜드 적합도 가중치")
    sentiment_weight: float = Field(0.3, ge=0, le=1, description="감성분석 가중치")
    roi_weight: float = Field(0.4, ge=0, le=1, description="ROI 가중치")

    def validate_weights(self):
        """가중치 합이 1인지 검증"""
        total = self.brand_image_weight + self.sentiment_weight + self.roi_weight
        if abs(total - 1.0) > 0.01:  # 부동소수점 오차 허용
            raise ValueError(f"가중치 합이 1이 아닙니다: {total}")
        
class TotalScore(BaseModel):
    """최종 종합 점수"""
    channel_id: str
    channel_title: Optional[str] = None
    thumbnail_url: Optional[str] = None

    # 개별 점수
    brand_image_score: float = Field(..., ge=0, le=100)
    sentiment_score: float = Field(..., ge=0, le=100)
    roi_score: float = Field(..., ge=0, le=100)

    # 가중치
    weights: WeightConfig

    # 최종 점수
    total_score: float = Field(..., ge=0, le=100, description="가중 평균 최종 점수")

    # 추가 정보
    subscriber_count: Optional[int] = None
    engagement_rate: Optional[float] = None
    estimated_cost: Optional[int] = None
    calculated_at: datetime = Field(default_factory=datetime.now)
    
    # 점수 해석
    grade: str = Field(..., description="A+, A, B+, B, C+, C, D")
    recommendation: str = Field(..., description="추천 여부 및 이유")

class SimulatorRequest(BaseModel):
    """시뮬레이터 요청"""
    channel_id: str
    brand_name: str
    brand_image_url: Optional[str] = Field(None, description="브랜드 이미지 URL")
    weights: WeightConfig = Field(default_factory=WeightConfig)
    num_videos: int = Field(3, ge=1, le=10, description="분석할 영상 수")
    max_comments_per_video: int = Field(200, ge=50, le=500, description="영상당 댓글 수")

class SimulatorResponse(BaseModel):
    """시뮬레이터 응답"""
    channel_id: str
    channel_title: Optional[str] = None
    
    # 상세 점수
    brand_image: Optional[BrandImageScore] = None
    sentiment: Optional[SentimentScore] = None
    roi_estimate: Optional[ROIEstimate] = None
    
    # 최종 점수
    total_score: TotalScore
    
    # 메타 정보
    processing_time_seconds: float
    errors: List[str] = Field(default_factory=list)

# ============================================
# 점수 계산 유틸리티 함수
# ============================================
def calculate_total_score(
    brand_score: float,
    sentiment_score: float,
    roi_score: float,
    weights: WeightConfig
) -> float:
    """가중 평균으로 최종 점수 계산"""
    weights.validate_weights()
    
    total = (
        brand_score * weights.brand_image_weight +
        sentiment_score * weights.sentiment_weight +
        roi_score * weights.roi_weight
    )
    
    return round(total, 2)

def assign_grade(score: float) -> str:
    """점수를 등급으로 변환"""
    if score >= 95:
        return "A+"
    elif score >= 90:
        return "A"
    elif score >= 85:
        return "B+"
    elif score >= 80:
        return "B"
    elif score >= 75:
        return "C+"
    elif score >= 70:
        return "C"
    else:
        return "D"
    
def generate_recommendation(total_score: float, scores: Dict[str, float]) -> str:
    """점수 기반 추천 메시지 생성"""
    if total_score >= 85:
        return "✅ 강력 추천: 매우 높은 마케팅 효과가 예상됩니다."
    elif total_score >= 75:
        return "👍 추천: 좋은 마케팅 효과가 예상됩니다."
    elif total_score >= 65:
        return "⚠️ 조건부 추천: 일부 지표 개선 시 효과적일 수 있습니다."
    else:
        # 낮은 점수 원인 분석
        weak_points = []
        if scores.get("brand_image", 100) < 60:
            weak_points.append("브랜드 적합도")
        if scores.get("sentiment", 100) < 60:
            weak_points.append("댓글 감성")
        if scores.get("roi", 100) < 60:
            weak_points.append("ROI")
        
        if weak_points:
            return f"❌ 비추천: {', '.join(weak_points)} 개선 필요"
        else:
            return "❌ 비추천: 종합 점수가 낮습니다."
        
def calculate_roi_score_from_engagement(
    engagement_rate: float,
    subscriber_count: int,
    estimated_cost: int
) -> Dict[str, Any]:
    """
    참여율 기반 ROI 점수 계산
    
    공식:
    - 예상 조회수 = 구독자 수 * (engagement_rate / 100) * 10
    - 예상 참여 = 예상 조회수 * (engagement_rate / 100)
    - CPE (Cost Per Engagement) = 비용 / 예상 참여
    - ROI Score = 정규화된 점수 (0-100)
    """

    # 예상 조회수 (구독자의 일정 비율)
    estimated_views = int(subscriber_count * (engagement_rate / 100) * 10)
    
    # 예상 참여 (조회수 * 참여율)
    estimated_engagement = int(estimated_views * (engagement_rate / 100))

    # Cost Per Engagement
    cpe = estimated_cost / estimated_engagement if estimated_engagement > 0 else float('inf')
    
    # Cost Per View
    cpv = estimated_cost / estimated_views if estimated_views > 0 else float('inf')
   
    # ROI Score 계산 (CPE가 낮을수록 높은 점수)
    # 기준: CPE 100원 이하 = 100점, 1000원 이상 = 0점
    if cpe < 100:
        roi_score = 100.0
    elif cpe > 1000:
        roi_score = 0.0
    else:
        roi_score = 100.0 - ((cpe - 100) / 900 * 100)
    
    return {
        "estimated_views": estimated_views,
        "estimated_engagement": estimated_engagement,
        "cost_estimate": estimated_cost,
        "roi_score": round(roi_score, 2),
        "engagement_rate": engagement_rate,
        "cpe": round(cpe, 2),
        "cpv": round(cpv, 4)
    }