import os
import logging
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.recommender import HybridRecommender
from app.cache import RedisCache
from app.auth import create_access_token, create_user, authenticate_user, get_current_user
from app.logging_config import configure_logging
from pydantic import BaseModel


class AuthModel(BaseModel):
    username: str
    password: str


APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 8000))
MODEL_PATH = os.getenv("MODEL_PATH", "./models/hybrid_model.joblib")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

configure_logging(os.getenv('LOG_LEVEL', 'INFO'))
log = logging.getLogger(__name__)

app = FastAPI(title="Hybrid Movie Recommender")

# CORS (allow frontend origins)
FRONTEND_ORIGINS = [
    os.getenv('VITE_API_BASE', ''),
    os.getenv('FRONTEND_ORIGIN', 'http://localhost:3000'),
    'http://localhost:5173'
]
FRONTEND_ORIGINS = [o for o in FRONTEND_ORIGINS if o]
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS or ['http://localhost:3000', 'http://localhost:5173'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

cache = RedisCache(REDIS_URL)
recommender = HybridRecommender(model_path=MODEL_PATH, cache=cache)


@app.on_event("startup")
def startup_event():
    log.info('Starting application')
    recommender.load_or_train()


@app.get("/recommend/{user_id}")
def recommend(user_id: int, n: int = 10, current_user: dict = Depends(get_current_user)):
    try:
        results = recommender.recommend(user_id, n=n)
        return {"user_id": user_id, "recommendations": results}
    except Exception as e:
        log.exception('Recommendation failed')
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/signup')
def signup(payload: AuthModel):
    user = create_user(payload.username, payload.password)
    return {"id": user['id'], "username": user['username']}


@app.post('/login')
def login(payload: AuthModel):
    user = authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    access_token = create_access_token({"sub": str(user['id'])})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/retrain")
def retrain(request: Request):
    token = request.headers.get("X-Retrain-Token")
    if token != os.getenv("RETRAIN_TOKEN"):
        raise HTTPException(status_code=403, detail="Invalid retrain token")
    ok = recommender.retrain_and_reload()
    if not ok:
        raise HTTPException(status_code=500, detail='Retrain failed')
    return {"status": "retrained"}


@app.get("/metrics")
def metrics():
    data = generate_latest()
    return JSONResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
