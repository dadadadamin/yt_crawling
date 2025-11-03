import re, os, math
from collections import Counter
from statistics import mean
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# -----------------------------
# 텍스트 전처리 / 토큰화
# -----------------------------
def tokenize_ko(text: str) -> list[str]:
    text = re.sub(r"https?://\S+|#[\w가-힣_]+", " ", text)
    text = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text)
    toks = [t for t in text.lower().split() if len(t) > 1]
    return toks

# -----------------------------
# TF-IDF or 빈도 기반 핵심 키워드 추출
# -----------------------------
def extract_keywords_tfidf(texts: List[str], top_k: int = 15) -> List[str]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(max_features=2000, stop_words=None)
        X = vec.fit_transform(texts)
        scores = X.sum(axis=0).A1
        terms = vec.get_feature_names_out()
        ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)
        return [k for k, _ in ranked[:top_k]]
    except Exception:
        toks = " ".join(texts).split()
        common = Counter(toks).most_common(top_k)
        return [w for w, _ in common]

# -----------------------------
# 규칙 기반 점수들
# -----------------------------
def weighted_keyword_score(text: str, brand_words: set[str]) -> float:
    toks = tokenize_ko(text)
    cnt = Counter(toks)
    match = sum(cnt[w] for w in brand_words if w in cnt)
    norm = len(toks) or 1
    return min(match / norm * 10, 1.0)

def stance_score(text: str) -> float:
    plus = ["내돈내산","솔직","리뷰","정보","가이드","노하우","경험"]
    minus = ["광고","과장","사기","허위","논란","과도","뻥"]
    t = " ".join(tokenize_ko(text))
    p = sum(1 for w in plus if w in t)
    m = sum(1 for w in minus if w in t)
    base = (p - m + 3) / 6
    return max(0.0, min(1.0, base))

def tag_match_score(tags: list[str], brand_words: set[str]) -> float:
    tags_norm = set([t.lower() for t in tags or []])
    inter = len(tags_norm & brand_words)
    return min(inter / max(len(brand_words), 1), 1.0)

# -----------------------------
# OpenAI 기반 적합도 보조 분석
# -----------------------------
def analyze_with_openai(summary_text: str, brand_keywords: List[str]) -> Dict[str, Any]:
    if not client:
        return {"llm_score": None, "reason": "(OpenAI 키 없음)"}
    prompt = f"""
    다음 영상의 내용 요약과 브랜드 키워드를 참고하여 브랜드 이미지 적합도를 평가해 주세요.
    - 분석할 텍스트: {summary_text[:2000]}
    - 브랜드 키워드: {', '.join(brand_keywords)}

    0에서 100 사이 점수와 한 줄 이유를 JSON 형식으로만 출력하세요.
    예시: {{ "score": 82, "reason": "건강/친환경 이미지와 잘 부합" }}
    """
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        ans = res.choices[0].message.content
        import json
        j = json.loads(re.search(r"\{.*\}", ans, re.S).group())
        return {"llm_score": j.get("score"), "reason": j.get("reason")}
    except Exception as e:
        return {"llm_score": None, "reason": f"(LLM 호출 실패: {e})"}

# -----------------------------
# 하이브리드 종합 브랜드 적합도
# -----------------------------
def hybrid_brand_fit(
    title: str,
    desc: str,
    transcript: str,
    tags: list[str],
    brand_keywords: List[str],
    knu_tone: Optional[float] = None,
    use_llm: bool = True
) -> Dict[str, Any]:
    brand_set = set([w.lower() for w in brand_keywords])
    text = f"{title}\n{desc}\n{transcript or ''}"

    # 1. 핵심 키워드 추출
    top_keywords = extract_keywords_tfidf([text])
    topical = weighted_keyword_score(text, brand_set)
    stance = stance_score(text)
    tagfit = tag_match_score(tags, brand_set)
    tone = max(0.0, min(1.0, knu_tone or 0.0))

    # 2. LLM 분석 (선택)
    llm_part = {"llm_score": None, "reason": None}
    if use_llm:
        llm_part = analyze_with_openai(" ".join(top_keywords[:10]), brand_keywords)
        llm_score = (llm_part.get("llm_score") or 0) / 100
    else:
        llm_score = 0

    # 3. 가중합
    brand_fit = (
        0.4 * topical +
        0.2 * tagfit +
        0.1 * stance +
        0.1 * tone +
        0.2 * llm_score
    ) * 100

    return {
        "brand_fit_score": round(brand_fit, 1),
        "components": {
            "topical": round(topical * 100, 1),
            "tags": round(tagfit * 100, 1),
            "stance": round(stance * 100, 1),
            "tone": round(tone * 100, 1),
            "llm": round(llm_score * 100, 1)
        },
        "top_keywords": top_keywords,
        "matched_tags": list(set(tags or []) & brand_set),
        "llm_reason": llm_part.get("reason"),
    }
