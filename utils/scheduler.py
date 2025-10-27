import sys
import os
from pathlib import Path

# 이 파일(scheduler.py)의 위치를 기준으로 프로젝트 루트 폴더의 경로를 계산
# ( .../yt_crawling/utils/scheduler.py -> .../yt_crawling/ )
ROOT_DIR = Path(__file__).resolve().parent.parent
# 파이썬이 모듈을 찾을 수 있도록 루트 폴더를 시스템 경로에 추가
sys.path.append(str(ROOT_DIR))

import schedule
import time
from datetime import datetime
from sqlmodel import Session, select
from db.db import engine, Influencer  # DB 엔진과 모델 가져오기

# 'calculate_engagement_rate' (이전 버전 함수) 제거
# 'VideoStatsOut' (Video 테이블용) 제거
from utils.youtube_utils import (
    search_channels_by_keyword, # 키워드 기준 API 호출 함수
    fetch_channel_details,
    get_recent_video_stats,
    calculate_engagement_rate_from_stats
)
# from models.youtube_models import VideoStatsOut # <-- Video 테이블용이므로 제거

print("[Scheduler] 스케줄러 시작. 6시간마다 데이터를 업데이트합니다.")

# 수집할 카테고리(키워드) 목록 정의
CATEGORIES_TO_CRAWL = {
    "건강": 10,  # "건강" 키워드로 10명
    "뷰티": 10,  # "뷰티" 키워드로 10명
    "게임": 10,
    "여행": 10,
    "요리": 10,
    "IT": 10,
    "음악": 10,
    "영화": 10,
    "스포츠": 10,
    "경제": 10   # 총 100명
}

# (참고) sync_videos_to_db 함수 정의가 있었다면 이 부분에서 삭제

def update_influencer_data():
    """
    (신규) '키워드' 기반으로 유튜버를 검색하고,
    해당 키워드를 'category' 컬럼에 저장
    """
    print(f"[{datetime.now()}] 키워드 기반 데이터 업데이트 작업 시작...")
    
    # 1. DB 세션 시작
    with Session(engine) as session:
        
        # 2. 정의된 카테고리(키워드) 목록을 순회
        for category_keyword, top_n in CATEGORIES_TO_CRAWL.items():
            
            print(f"\n[INFO] '{category_keyword}' 카테고리(키워드) 수집 시작 (목표: {top_n}명)")
            
            try:
                # 3. (신규) 키워드로 채널 ID 10개 검색 (API 호출)
                channel_ids = search_channels_by_keyword(
                    keyword=category_keyword, 
                    top_n=top_n
                )
                print(f"[INFO] '{category_keyword}' 키워드로 {len(channel_ids)}명 ID 수집 완료.")
            except Exception as e:
                print(f"[ERROR] '{category_keyword}' 검색 중 오류: {e}")
                continue # 다음 키워드로 넘어감
            
            # 4. 검색된 10개의 채널 ID를 순회
            for channel_id in channel_ids:
                try:
                    # 5. 채널 상세 정보 가져오기 (API 호출)
                    details_list = fetch_channel_details([channel_id], source_tag=f"search:{category_keyword}")
                    if not details_list:
                        continue
                    details = details_list[0]
                
                    # 5-1. (신규) 구독자 수 필터링
                    sub_count = details.subscriber_count or 0
                    if not (100000 <= sub_count <= 1000000):
                        print(f"[SKIP] {details.title} (구독자: {sub_count}) - 범위(10만~100만) 미달")
                        continue # 다음 채널로

                    # 6. DB에서 기존 인플루언서 정보 확인
                    db_influencer = session.get(Influencer, channel_id)

                    # 7. 영상 통계 및 참여율 계산 (API 호출)
                    video_stats = get_recent_video_stats(channel_id, num_videos=5)
                    eng_rate = calculate_engagement_rate_from_stats(
                        video_stats, 
                        (details.subscriber_count or 0)
                    )

                    # 8. Influencer 테이블 저장/업데이트 (DB 작업 1)
                    if db_influencer:
                        # (UPDATE)
                        db_influencer.title = details.title
                        db_influencer.subscriber_count = details.subscriber_count
                        db_influencer.view_count = details.view_count
                        db_influencer.video_count = details.video_count
                        db_influencer.thumbnail_url = details.thumbnail_url
                        db_influencer.engagement_rate = eng_rate
                        db_influencer.last_updated = datetime.now()
                        db_influencer.category = category_keyword # <-- ★★★ 핵심 ★★★
                        print(f"[UPDATE] {details.title} (카테고리: {category_keyword})")
                    
                    else:
                        # (CREATE)
                        db_influencer = Influencer(
                            channel_id=details.channel_id,
                            title=details.title,
                            description=details.description,
                            subscriber_count=details.subscriber_count,
                            view_count=details.view_count,
                            video_count=details.video_count,
                            thumbnail_url=details.thumbnail_url,
                            published_at=datetime.fromisoformat(details.published_at.replace('Z', '+00:00')) if details.published_at else None,
                            country=details.country,
                            engagement_rate=eng_rate,
                            last_updated=datetime.now(),
                            category=category_keyword, # <-- 키워드 저장
                            estimated_price="가격 문의" # 예상 매출액은 수동 설정
                        )
                        session.add(db_influencer)
                        print(f"[CREATE] {details.title} (카테고리: {category_keyword})")
                    
                    # --- (3) Video 테이블 저장 로직 제거 ---
                    # 9. Video 테이블 저장/업데이트 (DB 작업 2)
                    # if video_stats:
                    #     sync_videos_to_db(session, video_stats, channel_id) # <-- 이 부분 제거

                except Exception as e:
                    print(f"[ERROR] {channel_id} 처리 중 오류: {e}")
                    session.rollback() # 이 채널만 롤백
            
            # 10. (중요) 하나의 카테고리(키워드)가 끝나면 DB에 저장
            print(f"[COMMIT] '{category_keyword}' 카테고리 작업 완료. DB에 저장합니다.")
            session.commit()
    
    print(f"\n[{datetime.now()}] 모든 키워드 데이터 업데이트 작업 완료.")


# --- 스케줄러 실행 ---
# 1. 서버 시작 시 1회 즉시 실행 (DB 채우기용)
# DB를 처음 채울 때만 이 코드의 주석을 풀고 한 번 실행
update_influencer_data() 

# 2. 이후 6시간마다 update_influencer_data 함수 실행
print(f"[{datetime.now()}] 스케줄러 대기 상태. 6시간 주기로 실행됩니다.")
schedule.every(6).hours.do(update_influencer_data)

while True:
    schedule.run_pending()
    time.sleep(1)