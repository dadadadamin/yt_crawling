from fastapi import FastAPI
from routes.youtube_routes import youtube_router
from db.db import create_db_and_tables  
import uvicorn

app = FastAPI(title="Infloi YouTube API")

# (추가) 서버 시작 시 DB와 테이블 생성
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# 라우터 등록
app.include_router(youtube_router, prefix="/infloi")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)