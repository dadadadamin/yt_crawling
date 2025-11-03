from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# [검색 요청] 예: {"keyword": "건강", "top_n": 30}
class SearchReq(BaseModel):
    keyword: str
    top_n: int = Field(30, ge=1, le=200)
    region: str = "KR"
    lang: str = "ko"

# [인기 유튜버 요청] chart=mostPopular 기반
class KRPopularReq(BaseModel):
    top_n: int = 100
    region: str = "KR"
    pages: int = 5

# [채널 정보]
class ChannelDetails(BaseModel):
    channel_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    custom_url: Optional[str] = None
    published_at: Optional[str] = None
    country: Optional[str] = None
    subscriber_count: Optional[int] = None
    video_count: Optional[int] = None
    view_count: Optional[int] = None
    topic_ids: Optional[List[str]] = None
    thumbnail_url: Optional[str] = None
    source: Optional[str] = None

# [영상 통계 요청]
class VideoStatsReq(BaseModel):
    channel_ids: Optional[List[str]] = None
    video_ids: Optional[List[str]] = None
    max_videos_per_channel: int = 8

# [영상 통계 응답]
class VideoStatsOut(BaseModel):
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    video_id: str
    video_title: Optional[str] = None
    video_published_at: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    duration_seconds: Optional[int] = None

# [댓글 분석 요청]
class CommentsSummaryReq(BaseModel):
    channel_ids: Optional[List[str]] = None
    video_ids: Optional[List[str]] = None
    max_videos_per_channel: int = 5
    include_replies: bool = False
    max_comments_per_video: int = 800
    keyword_method: Literal["tfidf"] = "tfidf"
    keyword_top_k: int = 40
    sentiment: Literal["none", "basic"] = "none"

# [댓글 분석 결과]
class CommentsSummaryOut(BaseModel):
    keywords: List[Dict[str, Any]]
    sentiment: Optional[Dict[str, Any]] = None
    counts: Dict[str, int]

# 홈 화면 유튜버 카드 (응답 모델)
class HomeYoutuberCard(BaseModel):
    # 유튜브 API에서 가져오는 실제 데이터
    channel_id: str
    channel_title: Optional[str] = None
    subscriber_count: Optional[int] = None
    thumbnail_url: Optional[str] = None

    # 우리가 만들어야할 임시데이터 
    category: Optional[str] = Field(None, description="서비스 자체 카테고리 (예: 건강/라이프스타일)")
    engagement_rate: Optional[float] = Field(None, description="참여율 (%)")
    estimated_price: Optional[str] = Field(None, description="예상 가격 (예: ₩2,000,000)")


class ChannelWithMetrics(ChannelDetails):
    subscriber_count: Optional[int] = None  # 부모에도 있지만 명시적으로 유지
    engagement_rate: Optional[float] = None # % (최근 영상 평균)
    roi: Optional[float] = None             # 임시: subscriber_count 사용

# 최신 영상 댓글 분석 요청/응답
class LatestCommentsAnalyzeReq(BaseModel):
    channel_id: str = Field(..., description="분석할 채널의 고유 ID (예: UC...)")
    include_replies: bool = False
    max_comments: int = Field(500, ge=1, le=5000)  # 한 영상에서 수집할 최대 댓글 수
    save_csv: bool = True                           # CSV 저장 여부
    out_dir: str = "./data"                         # CSV 저장 폴더

class LatestCommentsAnalyzeRes(BaseModel):
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    comments_used: int
    csv_path: Optional[str] = None
    keywords: List[Dict[str, Any]]                 # [{keyword, score, method}]


#자막 기반 브랜드 적합도 분석
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class BrandAnalysisReq(BaseModel):
    video_id: str
    brand_keywords: List[str]
    use_llm: bool = Field(default=True, description="OpenAI API 사용 여부")

class BrandAnalysisOut(BaseModel):
    video_id: str
    title: str
    description: str
    brand_fit_score: float
    components: Dict[str, float]
    top_keywords: List[str]
    matched_tags: List[str]
    llm_reason: Optional[str]
