from sqlmodel import SQLModel, create_engine, Field, Relationship, Session, select
from typing import List, Optional
from datetime import datetime

# 1. DB 파일 이름 정의 (SQLite 파일 기반 DB)
sqlite_file_name = "influencer.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

# 2. DB 엔진 생성 (connect_args는 SQLite에서만 필요)
engine = create_engine(sqlite_url, echo=True, connect_args={"check_same_thread": False})

# 3. 테이블 모델 정의 

# Video 테이블과 Influencer 간의 관계를 위한 중간 테이블
class VideoLink(SQLModel, table=True):
    video_id: Optional[str] = Field(default=None, foreign_key="video.video_id", primary_key=True)
    influencer_id: Optional[str] = Field(default=None, foreign_key="influencer.channel_id", primary_key=True)

# Video 테이블 정의 
class Video(SQLModel, table=True):
    video_id: str = Field(primary_key=True)
    video_title: Optional[str] = None
    video_published_at: Optional[datetime] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None

    # Influencer와의 관계 (Video 1 : N Influencer. 'VideoLink'를 통해)
    channel_id: Optional[str] = Field(default=None, foreign_key="influencer.channel_id")
    channel: Optional["Influencer"] = Relationship(back_populates="videos")

# Influencer 테이블 정의
class Influencer(SQLModel, table=True):
    channel_id: str = Field(primary_key=True)
    title: Optional[str] = None
    description: Optional[str] = None 
    subscriber_count: Optional[int] = None
    view_count: Optional[int] = None
    video_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    published_at: Optional[datetime] = None
    # topic_ids: Optional[List[str]] = Field(default=None, sa_column=Column(JSON)) # JSON은 약간 복잡하므로 일단 생략
    country: Optional[str] = None

    # 별도로 추가해야하는 컬럼
    category: Optional[str] = None # 건강/라이프 등
    estimated_price: Optional[str] = None # 예상 가격
    engagement_rate: Optional[float] = None # 참여율
    last_updated: Optional[datetime] = None # 마지막 업로드시기

    # Video와의 관계 (Influencer 1 : N Video)
    videos: List[Video] = Relationship(back_populates="channel")

# 4. DB와 테이블을 생성하는 함수
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# 5. DB 세션을 관리하기 위한 함수 (FastAPI의 의존성 주입에 사용)
def get_session():
    with Session(engine) as session:
        yield session