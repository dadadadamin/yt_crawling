"""
브랜드 이미지 적합도 분석 모듈
- CLIP 기반 이미지 유사도 분석
- 텍스트 임베딩 기반 브랜드-채널 매칭
- 최종 적합도 점수 산출 (0-100)
"""

import torch
from PIL import Image
import requests
from io import BytesIO
from typing import List, Dict, Optional, Tuple
import numpy as np
from transformers import CLIPProcessor, CLIPModel
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import re

# ============================================
# 모델 초기화 (전역 변수)
# ============================================

print("[Brand Analysis] 모델 로딩 중...")

# 1. CLIP 모델 (이미지-텍스트 유사도)
CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"
clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
clip_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
clip_model = clip_model.to(clip_device)
clip_model.eval()

# 2. Sentence Transformer (텍스트 유사도)
SBERT_MODEL = "sentence-transformers/xlm-r-100langs-bert-base-nli-stsb-mean-tokens"
sbert_model = SentenceTransformer(SBERT_MODEL)

print(f"[Brand Analysis] 모델 로딩 완료 (Device: {clip_device})")

# ============================================
# 이미지 처리 유틸리티
# ============================================

def load_image_from_url(url: str) -> Optional[Image.Image]:
    """URL에서 이미지 로드"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content)).convert("RGB")
        return image
    except Exception as e:
        print(f"[Error] 이미지 로드 실패 ({url}): {e}")
        return None


def load_image_from_base64(base64_str: str) -> Optional[Image.Image]:
    """Base64 문자열에서 이미지 로드"""
    try:
        import base64
        image_data = base64.b64decode(base64_str)
        image = Image.open(BytesIO(image_data)).convert("RGB")
        return image
    except Exception as e:
        print(f"[Error] Base64 이미지 로드 실패: {e}")
        return None


# ============================================
# 1. 이미지 유사도 분석 (CLIP)
# ============================================

def calculate_image_similarity_clip(
    brand_image: Image.Image,
    channel_thumbnails: List[Image.Image]
) -> float:
    """
    CLIP 모델을 사용한 이미지 유사도 계산
    
    Args:
        brand_image: 브랜드 제품 이미지
        channel_thumbnails: 채널의 최신 영상 썸네일 리스트
    
    Returns:
        평균 유사도 점수 (0-100)
    """
    if not channel_thumbnails:
        return 50.0  # 기본값
    
    try:
        # 브랜드 이미지 임베딩
        brand_inputs = clip_processor(images=brand_image, return_tensors="pt").to(clip_device)
        with torch.no_grad():
            brand_features = clip_model.get_image_features(**brand_inputs)
            brand_features = brand_features / brand_features.norm(dim=-1, keepdim=True)
        
        # 채널 썸네일 임베딩 및 유사도 계산
        similarities = []
        for thumbnail in channel_thumbnails:
            thumb_inputs = clip_processor(images=thumbnail, return_tensors="pt").to(clip_device)
            with torch.no_grad():
                thumb_features = clip_model.get_image_features(**thumb_inputs)
                thumb_features = thumb_features / thumb_features.norm(dim=-1, keepdim=True)
            
            # 코사인 유사도
            similarity = torch.nn.functional.cosine_similarity(
                brand_features, thumb_features
            ).item()
            
            # -1~1 범위를 0~100으로 변환
            similarity_score = (similarity + 1) * 50
            similarities.append(similarity_score)
        
        # 평균 유사도 반환 (numpy float를 Python float로 변환)
        avg_similarity = float(np.mean(similarities))
        return round(avg_similarity, 2)
    
    except Exception as e:
        print(f"[Error] 이미지 유사도 계산 실패: {e}")
        return 50.0


def analyze_image_style_compatibility(
    brand_image: Image.Image,
    brand_style_keywords: List[str],
    channel_thumbnails: List[Image.Image]
) -> Dict[str, float]:
    """
    CLIP을 사용한 이미지 스타일 분석
    
    Args:
        brand_image: 브랜드 이미지
        brand_style_keywords: 브랜드 스타일 키워드 (예: "모던한", "미니멀한")
        channel_thumbnails: 채널 썸네일들
    
    Returns:
        스타일별 매칭 점수
    """
    style_scores = {}
    
    try:
        # 브랜드 스타일 키워드를 텍스트 프롬프트로 변환
        for keyword in brand_style_keywords:
            text_prompt = f"a {keyword} style image"
            
            # 텍스트-이미지 유사도 계산
            inputs = clip_processor(
                text=[text_prompt],
                images=channel_thumbnails,
                return_tensors="pt",
                padding=True
            ).to(clip_device)
            
            with torch.no_grad():
                outputs = clip_model(**inputs)
                logits_per_image = outputs.logits_per_image
                probs = logits_per_image.softmax(dim=1).cpu().numpy()
            
            # 평균 확률을 점수로 변환 (numpy float를 Python float로 변환)
            avg_prob = float(np.mean(probs)) * 100
            style_scores[keyword] = round(avg_prob, 2)
    
    except Exception as e:
        print(f"[Error] 스타일 분석 실패: {e}")
    
    return style_scores


# ============================================
# 2. 텍스트 유사도 분석 (Sentence-BERT)
# ============================================

def calculate_text_similarity(
    brand_description: str,
    brand_tone: str,
    channel_description: str,
    recent_video_titles: List[str]
) -> float:
    """
    브랜드 설명과 채널 콘텐츠의 텍스트 유사도 계산
    
    Args:
        brand_description: 브랜드/제품 설명
        brand_tone: 브랜드 톤앤매너
        channel_description: 채널 설명
        recent_video_titles: 최근 영상 제목들
    
    Returns:
        텍스트 유사도 점수 (0-100)
    """
    try:
        # 브랜드 텍스트 결합
        brand_text = f"{brand_description} {brand_tone}"
        
        # 채널 텍스트 결합
        channel_text = f"{channel_description} " + " ".join(recent_video_titles)
        
        # 임베딩 생성
        brand_embedding = sbert_model.encode([brand_text])
        channel_embedding = sbert_model.encode([channel_text])
        
        # 코사인 유사도 계산 (numpy 타입을 Python float로 변환)
        similarity = float(cosine_similarity(brand_embedding, channel_embedding)[0][0])
        
        # 0~1 범위를 0~100으로 변환
        similarity_score = similarity * 100
        
        return round(max(0, min(100, similarity_score)), 2)
    
    except Exception as e:
        print(f"[Error] 텍스트 유사도 계산 실패: {e}")
        return 50.0


def analyze_tone_compatibility(
    brand_tone: str,
    channel_description: str,
    video_titles: List[str]
) -> Dict[str, float]:
    """
    브랜드 톤앤매너와 채널 톤의 매칭도 분석
    
    Args:
        brand_tone: 브랜드 톤 (예: "친근하고 밝은", "전문적이고 신뢰감 있는")
        channel_description: 채널 설명
        video_titles: 최근 영상 제목들
    
    Returns:
        톤 매칭 점수 및 세부 분석
    """
    # 톤 카테고리 정의
    tone_categories = {
            "친근한": {
            "keywords": ["친근", "편안", "재밌", "웃", "일상", "솔직", "편하", "캐주얼"],
            "synonyms": ["밝은", "활발", "즐거운", "유쾌", "경쾌"]
        },
        "전문적인": {
            "keywords": ["전문", "정보", "분석", "리뷰", "가이드", "팁", "노하우"],
            "synonyms": ["상세한", "체계적", "정확한", "신뢰", "꼼꼼"]
        },
        "감성적인": {
            "keywords": ["감성", "힐링", "따뜻", "위로", "공감", "감동", "진심"],
            "synonyms": ["편안한", "차분한", "잔잔한", "감각적"]
        },
        "역동적인": {
            "keywords": ["도전", "모험", "열정", "에너지", "활기", "신나", "화끈"],
            "synonyms": ["활발", "적극적", "역동", "파워풀", "생동감"]
        },
        "세련된": {
            "keywords": ["스타일", "트렌드", "감각", "세련", "모던", "럭셔리", "고급"],
            "synonyms": ["시크", "우아", "감각적", "트렌디", "멋진"]
        },
        "유머러스한": {
            "keywords": ["웃긴", "재밌", "유머", "코믹", "재치", "유쾌"],
            "synonyms": ["웃음", "재미", "유머러스", "개그", "ㅋㅋ"]
        },
        "진지한": {
            "keywords": ["진지", "심각", "진실", "솔직", "리얼"],
            "synonyms": ["현실", "사실", "있는그대로", "깊이있는"]
        }
    }
    
    # 채널 텍스트 준비
    channel_text = f"{channel_description} " + " ".join(video_titles)
    channel_text_lower = channel_text.lower()
    
    # 2. 각 톤별 점수 계산
    tone_scores = {}
    
    for tone_name, tone_data in tone_categories.items():
        all_keywords = tone_data["keywords"] + tone_data["synonyms"]
        
        # 키워드 매칭 점수
        match_count = sum(1 for kw in all_keywords if kw in channel_text_lower)
        keyword_score = min(100, (match_count / len(all_keywords)) * 150)  # 가중치 증가
        
        tone_scores[tone_name] = round(keyword_score, 2)
    
    # 3. 브랜드 톤과 가장 유사한 카테고리 찾기 (개선)
    brand_tone_lower = brand_tone.lower()
    matched_scores = []
    
    # 3-1. 직접 키워드 매칭
    for tone_name, tone_data in tone_categories.items():
        all_keywords = tone_data["keywords"] + tone_data["synonyms"]
        
        # 브랜드 톤에 키워드가 포함되어 있으면 해당 점수 추가
        for keyword in all_keywords:
            if keyword in brand_tone_lower:
                matched_scores.append(tone_scores[tone_name])
                break
    
    # 3-2. Sentence-BERT 유사도 추가 (더 유연한 매칭)
    try:
        brand_embedding = sbert_model.encode([brand_tone])
        channel_embedding = sbert_model.encode([channel_text])
        
        semantic_similarity = float(
            cosine_similarity(brand_embedding, channel_embedding)[0][0]
        )
        semantic_score = semantic_similarity * 100
        
        matched_scores.append(semantic_score)
        
    except Exception as e:
        print(f"[Warning] 톤 의미 유사도 계산 실패: {e}")
    
    # 4. 최종 점수 결정
    if matched_scores:
        # 매칭된 점수들의 평균
        overall_tone_match = float(np.mean(matched_scores))
    else:
        # 매칭 안되면 전체 톤 점수 중 최고값 사용 (최소 보장)
        overall_tone_match = max(tone_scores.values()) if tone_scores else 50.0
    
    # 5. 최소 점수 보장 (너무 낮지 않게)
    overall_tone_match = max(30.0, overall_tone_match)  # 최소 30점
    
    return {
        "overall_tone_match": round(overall_tone_match, 2),
        "tone_breakdown": tone_scores
    }


# ============================================
# 3. 카테고리 매칭 분석
# ============================================

def analyze_category_match(
    brand_category: str,
    channel_category: Optional[str],
    video_titles: List[str]
) -> float:
    """
    브랜드 카테고리와 채널 카테고리의 매칭도
    
    Args:
        brand_category: 브랜드 카테고리 (예: "뷰티", "패션")
        channel_category: 채널 카테고리 (DB에 저장된 값)
        video_titles: 최근 영상 제목들
    
    Returns:
        카테고리 매칭 점수 (0-100)
    """
    score = 50.0  # 기본 점수
    
    # 1. DB 카테고리 직접 비교
    if channel_category and brand_category:
        if brand_category.lower() in channel_category.lower():
            score += 30.0
        elif channel_category.lower() in brand_category.lower():
            score += 20.0
    
    # 2. 영상 제목에서 카테고리 키워드 검색
    brand_keywords = brand_category.lower().split()
    video_text = " ".join(video_titles).lower()
    
    keyword_matches = sum(1 for kw in brand_keywords if kw in video_text)
    if keyword_matches > 0:
        score += min(20.0, keyword_matches * 5)
    
    return round(min(100, score), 2)


# ============================================
# 4. 종합 브랜드 이미지 적합도 분석
# ============================================

def analyze_brand_compatibility(
    # 브랜드 정보 (필수)
    brand_name: str,
    brand_description: str,
    brand_tone: str,
    brand_category: str,
    
    # 채널 정보 (필수)
    channel_id: str,
    channel_description: str,
    channel_category: Optional[str],
    channel_thumbnails: List[str],  # URL 리스트
    video_titles: List[str],
    
    # 브랜드 이미지 (선택)
    brand_image_url: Optional[str] = None,
    brand_image_base64: Optional[str] = None
) -> Dict[str, any]:
    """
    종합 브랜드-채널 적합도 분석
    
    Returns:
        {
            "overall_score": 전체 적합도 (0-100),
            "image_similarity": 이미지 유사도,
            "text_similarity": 텍스트 유사도,
            "tone_match": 톤앤매너 매칭,
            "category_match": 카테고리 매칭,
            "detailed_analysis": {...}
        }
    """
    print(f"[Brand Analysis] {channel_id} 분석 시작...")
    
    results = {
        "channel_id": channel_id,
        "brand_name": brand_name,
        "overall_score": float(0.0),
        "image_similarity": float(0.0),
        "text_similarity": float(0.0),
        "tone_match": float(0.0),
        "category_match": float(0.0),
        "detailed_analysis": {}
    }
    
    # 1. 이미지 유사도 분석 (가중치 40%)
    if brand_image_url or brand_image_base64:
        try:
            # 브랜드 이미지 로드
            if brand_image_url:
                brand_image = load_image_from_url(brand_image_url)
            else:
                brand_image = load_image_from_base64(brand_image_base64)
            
            # 채널 썸네일 로드
            thumbnails = []
            for url in channel_thumbnails[:5]:  # 최대 5개
                img = load_image_from_url(url)
                if img:
                    thumbnails.append(img)
            
            if brand_image and thumbnails:
                image_score = calculate_image_similarity_clip(brand_image, thumbnails)
                results["image_similarity"] = float(image_score)
                
                # 스타일 분석 추가 (모든 값을 float로 변환)
                style_keywords = extract_style_keywords(brand_tone)
                style_analysis = analyze_image_style_compatibility(
                    brand_image, style_keywords, thumbnails
                )
                style_match_converted = {k: float(v) for k, v in style_analysis.items()}
                results["detailed_analysis"]["style_match"] = style_match_converted
        
        except Exception as e:
            print(f"[Error] 이미지 분석 실패: {e}")
            results["image_similarity"] = float(50.0)
    else:
        results["image_similarity"] = float(50.0)  # 이미지 없으면 중립
    
    # 2. 텍스트 유사도 분석 (가중치 30%)
    text_score = calculate_text_similarity(
        brand_description, brand_tone, channel_description, video_titles
    )
    results["text_similarity"] = float(text_score)
    
    # 3. 톤앤매너 매칭 (가중치 20%)
    tone_analysis = analyze_tone_compatibility(
        brand_tone, channel_description, video_titles
    )
    results["tone_match"] = float(tone_analysis["overall_tone_match"])
    # tone_breakdown의 모든 값도 float로 변환
    tone_breakdown = {k: float(v) for k, v in tone_analysis["tone_breakdown"].items()}
    results["detailed_analysis"]["tone_breakdown"] = tone_breakdown
    
    # 4. 카테고리 매칭 (가중치 10%)
    category_score = analyze_category_match(
        brand_category, channel_category, video_titles
    )
    results["category_match"] = float(category_score)
    
    # 5. 최종 종합 점수 계산 (모든 값을 Python float로 보장)
    overall = float(
        results["image_similarity"] * 0.40 +
        results["text_similarity"] * 0.30 +
        results["tone_match"] * 0.20 +
        results["category_match"] * 0.10
    )
    results["overall_score"] = round(overall, 2)
    
    print(f"[Brand Analysis] {channel_id} 분석 완료: {results['overall_score']}점")
    
    return results


# ============================================
# 유틸리티 함수
# ============================================

def extract_style_keywords(brand_tone: str) -> List[str]:
    """브랜드 톤에서 스타일 키워드 추출"""
    style_keywords = []
    
    keyword_map = {
        "모던": "modern",
        "미니멀": "minimal",
        "빈티지": "vintage",
        "캐주얼": "casual",
        "엘레강스": "elegant",
        "러블리": "lovely",
        "시크": "chic"
    }
    
    tone_lower = brand_tone.lower()
    for kr, en in keyword_map.items():
        if kr in tone_lower or en in tone_lower:
            style_keywords.append(en)
    
    return style_keywords if style_keywords else ["modern", "clean"]