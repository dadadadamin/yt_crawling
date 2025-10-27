import schedule
import time
from datetime import datetime
from sqlmodel import Session, select
from db import engine, Influencer  # DB 엔진과 모델 가져오기
from utils.youtube_utils import (
    collect_channels_from_most_popular, 
    fetch_channel_details,
    calculate_engagement_rate
)

print("[Scheduler] 스케줄러 시작. 6시간마다 데이터를 업데이트합니다.")

def update_influencer_data():
    """
    유튜브 API에서 데이터를 가져와 DB를 업데이트하는 메인 작업
    """
    print(f"[{datetime.now()}] 데이터 업데이트 작업 시작...")

    # 1. 수집 대상 채널 ID 목록 가져오기 (예: 인기 유튜버 100명)
    # 이 함수는 API 토큰 많이 사용하므로 주의 
    try:
        channel_ids = collect_channels_from_most_popular(region_code="KR", pages=2)
        print(f"[INFO] {len(channel_ids)}명의 인기 유튜버 ID 수집 완료.")
    except Exception as e:
        print(f"[ERROR] 인기 유튜버 수집 중 오류: {e}")
        return 

    # 2. DB 세션 시작
    with Session(engine) as session:
        for channel_id in channel_ids:
            try:
                # 3. 유튜브 API로 최신 채널 정보 가져오기
                details_list = fetch_channel_details([channel_id], source_tag="scheduler")
                if not details_list:
                    continue

                details = details_list[0] # ChannelDetails 모델
            
                # 4. DB에 이미 있는지 확인
                db_influencer = session.get(Influencer, channel_id)

                # 5. (선택) 참여율 계산 (API 추가 호출)
                eng_rate = calculate_engagement_rate(
                    channel_id=channel_id,
                    subscriber_count=(details.subscriber_count or 0)
                )

                if db_influencer:
                    # 6-A. (UPDATE) 이미 있으면 데이터 업데이트
                    db_influencer.title = details.title
                    db_influencer.subscriber_count = details.subscriber_count
                    db_influencer.view_count = details.view_count
                    db_influencer.video_count = details.video_count
                    db_influencer.thumbnail_url = details.thumbnail_url
                    db_influencer.engagement_rate = eng_rate
                    db_influencer.last_updated = datetime.now()
                    print(f"[UPDATE] {details.title} (구독자: {details.subscriber_count})")
                
                else:
                    # 6-B. (CREATE) 없으면 새로 추가
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
                        # (주의) category, estimated_price는 직접 DB에 넣어줘야 함 잠시 대기
                        category="미분류", 
                        estimated_price="가격 문의"
                    )
                    session.add(db_influencer)
                    print(f"[CREATE] {details.title} (구독자: {details.subscriber_count})")

                # 7. 5명 처리할 때마다 DB에 중간 저장 (commit)
                if channel_ids.index(channel_id) % 5 == 0:
                    print(f"[ERROR] {channel_id} 처리 중 오류: {e}")
                    session.rollback() # 오류 발생 시 롤백
            
            except Exception as e:
                print(f"[ERROR] {channel_id} 처리 중 오류: {e}")
                session.rollback() # 오류 발생 시 롤백
        
        # 8. 모든 작업 완료 후 최종 커밋
        session.commit()
    print(f"[{datetime.now()}] 데이터 업데이트 작업 완료.")

# --- 스케줄러 실행 ---
# 1. 서버 시작 시 1회 즉시 실행, 이후에는 주석처리 하여 Youtube API 과도 호출 방지
update_influencer_data()

# 2. 이후 6시간마다 update_influencer_data 함수 실행
schedule.every(6).hours.do(update_influencer_data)

while True:
    schedule.run_pending()
    time.sleep(1)