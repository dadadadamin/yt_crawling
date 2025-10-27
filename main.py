from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.youtube_routes import youtube_router
from db.db import create_db_and_tables  
import uvicorn

app = FastAPI(title="InfluROI YouTube API")

# CORS 설정 
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # origins 목록에 있는 주소에서의 요청을 허용
    allow_credentials=True,    # 쿠키 허용
    allow_methods=["*"],       # 모든 메소드(GET, POST, PUT 등) 허용
    allow_headers=["*"],       # 모든 헤더 허용
)

# (추가) 서버 시작 시 DB와 테이블 생성
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# 라우터 등록
app.include_router(youtube_router, prefix="/youtube")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)