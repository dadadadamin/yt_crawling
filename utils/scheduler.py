import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

import schedule
import time
from datetime import datetime
from sqlmodel import Session, select
from db.db import engine, Influencer, create_db_and_tables

from utils.youtube_utils import (
    search_channels_by_keyword,
    fetch_channel_details,
    get_recent_video_stats,
    calculate_engagement_rate_from_stats
)

print("[Scheduler] 스케줄러 시작. 6시간마다 데이터를 업데이트합니다.")

# ===== 크롤링 전략: 브랜드 협찬 적합 인플루언서 수집 =====
# 
# 1. 키워드 전략: 대중적이면서 브랜드 친화적인 키워드 사용
#    - "뷰티", "패션" 같은 넓은 범위 키워드 선택
#    - 너무 세분화된 키워드(예: "홈카페") 지양
#
# 2. 구독자 범위: 10만~100만 (중견 인플루언서)
#    - 소통이 활발하고 참여율이 높은 구간
#    - 브랜드 협찬 가격대가 적정한 구간
#
# 3. 필터링 기준 단순화:
#    - 1단계: 구독자 수 (10만~100만)
#    - 2단계: 뉴스/교육 채널 제외
#    - 3단계: 최근 활동성 (영상 3개 이상)
#    - 4단계: 기본 참여율 (1% 이상)

CATEGORIES_TO_CRAWL = {
    # 라이프스타일 (가장 브랜드 친화적)
    "뷰티": 15,
    "패션": 12,
    "일상": 15,
    
    # 푸드
    "요리": 12,
    "먹방": 10,
    
    # 취미/여가
    "여행": 10,
    "운동": 8,
    "게임": 10,
    
    # 테크/리뷰
    "리뷰": 8,
}

# ===== 간소화된 필터링 함수 =====

def is_suitable_creator(details, video_stats):
    """
    브랜드 협찬 적합 크리에이터 판별 (간소화 버전)
    
    Returns:
        tuple: (적합 여부, 사유)
    """
    
    # 1. 뉴스/교육/기업 채널 제외 
    blacklist = ['뉴스', 'news', '방송', 'tv', 'mbc', 'kbs', 'sbs', 
                 '강의', '강좌', '교육', '학원', '공식', 'official']
    
    text = (details.title + " " + (details.description or "")).lower()
    
    for word in blacklist:
        if word in text:
            return False, f"제외키워드({word})"
    
    # 2. 최근 활동성 체크 (완화: 1개 이상)
    if not video_stats or len(video_stats) < 1:
        return False, "영상부족"
    
    # 3. 기본 참여율 체크 (완화: 0.3% 이상으로 낮춤)
    try:
        eng_rate = calculate_engagement_rate_from_stats(
            video_stats, 
            details.subscriber_count or 0
        )
        if eng_rate and eng_rate < 0.3:
            return False, f"참여율낮음({eng_rate:.1f}%)"
    except:
        pass
    
    return True, "적합"


def calculate_price_string(sub_count):
    """가격 문자열 반환"""
    if 5000 <= sub_count <= 100000:
        return "100만원"
    elif 100001 <= sub_count <= 400000:
        return "200만원"
    elif 400001 <= sub_count <= 500000:
        return "300만원"
    elif 500001 <= sub_count <= 1000000:
        return "500만원"
    elif 1000001 <= sub_count <= 2000000:
        return "1000만원"
    return "가격문의"


# ===== 메인 업데이트 함수 =====

def update_influencer_data():
    """
    간소화된 크리에이터 수집 로직
    """
    print(f"\n{'='*70}")
    print(f"🚀 크리에이터 데이터 수집 시작: {datetime.now()}")
    print(f"{'='*70}\n")
    
    total_collected = 0
    total_skipped = 0
    
    with Session(engine) as session:
        
        for category_keyword, target_count in CATEGORIES_TO_CRAWL.items():
            
            print(f"\n🔍 [{category_keyword}] 수집 시작 (목표: {target_count}명)")
            print("-" * 70)
            
            try:
                # 더 많이 검색 (필터링 후 목표 달성 위해)
                channel_ids = search_channels_by_keyword(
                    keyword=category_keyword, 
                    top_n=target_count * 5  # 5배수 검색
                )
                print(f"📋 검색완료: {len(channel_ids)}개 채널")
                
            except Exception as e:
                print(f"❌ 검색실패: {e}\n")
                continue
            
            collected = 0
            skipped = 0
            
            for idx, channel_id in enumerate(channel_ids, 1):
                
                # 목표 달성시 중단
                if collected >= target_count:
                    break
                
                try:
                    # 채널 정보 가져오기
                    details_list = fetch_channel_details(
                        [channel_id],
                        source_tag=f"search:{category_keyword}"  # 필수 파라미터 추가
                        )
                    if not details_list:
                        skipped += 1
                        continue
                    
                    details = details_list[0]
                    sub_count = details.subscriber_count or 0
                    
                    # 구독자 수 1차 필터 (완화: 5천명 이상으로 낮춤)
                    if not (5000 <= sub_count <= 5000000):
                        print(f"[{idx:2d}] ⏭️  {details.title[:25]:25s} | 구독자: {sub_count:>9,}명")
                        skipped += 1
                        continue
                    
                    # 영상 통계 가져오기
                    video_stats = get_recent_video_stats(channel_id, num_videos=5)
                    
                    # ✅ 핵심 수정: VideoStatsOut 객체를 딕셔너리로 변환
                    video_stats_dict = []
                    for v in video_stats:
                        video_stats_dict.append({
                            'video_id': v.video_id,
                            'title': v.video_title,
                            'view_count': v.view_count or 0,
                            'like_count': v.like_count or 0,
                            'comment_count': v.comment_count or 0
                        })
                    
                    # 적합성 판별
                    is_ok, reason = is_suitable_creator(details, video_stats_dict)
                    
                    if not is_ok:
                        print(f"[{idx:2d}] ❌ {details.title[:25]:25s} | {reason}")
                        skipped += 1
                        continue
                    
                    # 참여율 계산
                    try:
                        eng_rate = calculate_engagement_rate_from_stats(
                            video_stats_dict, sub_count
                        ) or 0.0
                    except Exception as e:
                        print(f"[{idx:2d}] ⚠️  참여율계산오류: {str(e)[:40]}")
                        eng_rate = 0.0
                    
                    # 가격 계산
                    price = calculate_price_string(sub_count)
                    
                    # DB 저장
                    db_influencer = session.get(Influencer, channel_id)
                    
                    if db_influencer:
                        # UPDATE
                        db_influencer.title = details.title
                        db_influencer.subscriber_count = sub_count
                        db_influencer.view_count = details.view_count
                        db_influencer.video_count = details.video_count
                        db_influencer.thumbnail_url = details.thumbnail_url
                        db_influencer.engagement_rate = eng_rate
                        db_influencer.last_updated = datetime.now()
                        db_influencer.category = category_keyword
                        db_influencer.estimated_price = price
                        action = "수정"
                    else:
                        # CREATE
                        db_influencer = Influencer(
                            channel_id=channel_id,
                            title=details.title,
                            description=details.description,
                            subscriber_count=sub_count,
                            view_count=details.view_count,
                            video_count=details.video_count,
                            thumbnail_url=details.thumbnail_url,
                            published_at=datetime.fromisoformat(
                                details.published_at.replace('Z', '+00:00')
                            ) if details.published_at else None,
                            country=details.country,
                            engagement_rate=eng_rate,
                            last_updated=datetime.now(),
                            category=category_keyword,
                            estimated_price=price
                        )
                        session.add(db_influencer)
                        action = "추가"
                    
                    print(f"[{idx:2d}] ✅ {details.title[:25]:25s} | 구독자: {sub_count:>7,}명 | 참여율: {eng_rate:>5.1f}% | {action}")
                    collected += 1
                    
                except Exception as e:
                    error_msg = str(e)
                    # 더 자세한 오류 정보 출력
                    if "like_cou" in error_msg or "attribute" in error_msg.lower():
                        print(f"[{idx:2d}] ⚠️  데이터형식오류: {error_msg[:50]}")
                    else:
                        print(f"[{idx:2d}] ⚠️  처리오류: {error_msg[:50]}")
                    skipped += 1
                    continue
            
            # 카테고리별 커밋
            session.commit()
            
            total_collected += collected
            total_skipped += skipped
            
            print(f"\n📊 [{category_keyword}] 완료: ✅ {collected}명 수집 | ⏭️ {skipped}명 제외")
    
    # 최종 요약
    print(f"\n{'='*70}")
    print(f"🎉 전체 수집 완료")
    print(f"   ✅ 총 수집: {total_collected}명")
    print(f"   ⏭️ 총 제외: {total_skipped}명")
    print(f"   ⏰ {datetime.now()}")
    print(f"{'='*70}\n")


# ===== 스케줄러 실행 =====

# 데이터베이스 테이블 생성 (중요!)
print("🔧 데이터베이스 초기화 중...")
create_db_and_tables()
print("✅ 데이터베이스 테이블 생성 완료\n")

print("🔥 초기 데이터 수집 시작...\n")
update_influencer_data()

print(f"⏰ 스케줄러 대기중 (6시간 주기)")
schedule.every(6).hours.do(update_influencer_data)

while True:
    schedule.run_pending()
    time.sleep(1)