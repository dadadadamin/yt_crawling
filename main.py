from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.youtube_routes import youtube_router
from routes.simulator_routes import simulator_router
from db.db import create_db_and_tables  
import uvicorn

app = FastAPI(
    title="InfluROI YouTube API",
    description="유튜버 마케팅 ROI 분석 및 시뮬레이터 API",
    version="2.0.0"
)

# CORS 설정 (React 연동을 위해)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React 개발 서버
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# (추가) 서버 시작 시 DB와 테이블 생성
@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    print("✅ Database initialized")
    print("🚀 ROI Simulator API is ready!")

# 라우터 등록
app.include_router(youtube_router, prefix="/youtube", tags=["YouTube"])
app.include_router(simulator_router, prefix="/simulator", tags=["Simulator"])

# 루트 엔드포인트
@app.get("/")
def root():
    return {
        "message": "InfluROI API v2.0",
        "endpoints": {
            "youtube": "/youtube",
            "simulator": "/simulator",
            "docs": "/docs"
        }
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)