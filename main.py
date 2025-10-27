from fastapi import FastAPI
from routes.youtube_routes import youtube_router
import uvicorn

app = FastAPI(title="InfluROI YouTube API")

# 라우터 등록
app.include_router(youtube_router, prefix="/youtube")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)