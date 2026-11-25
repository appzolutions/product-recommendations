"""Product recommendation API (FastAPI).

Run locally:   uvicorn app.main:app --reload
Docs:          http://localhost:8000/docs
"""
import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .repository import FixtureRepository, MongoRepository

try:                                   # read settings from a .env file if one exists
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def build_repository():
    uri = os.getenv("MONGODB_URI")
    if uri:
        return MongoRepository(uri, os.getenv("MONGODB_DB", "recommender"))
    return FixtureRepository()


app = FastAPI(title="Product Recommender API", version="1.0.0",
              description="Returns pre-computed ALS recommendations for Amazon Video Games users.")
app.state.repo = build_repository()

# Allow the React page (on another address) to call this API
allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed.split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time-Ms"],
)


@app.middleware("http")
async def add_process_time(request: Request, call_next):
    """Measure how long each request takes on the server (Objective 4)."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.2f}"
    return response


# ---------- response shapes (see api_contract.md) ----------
class Recommendation(BaseModel):
    rank: int
    product_id: str
    predicted_rating: float
    title: Optional[str] = None
    price: Optional[float] = None
    average_rating: Optional[float] = None


class PastRating(BaseModel):
    product_id: str
    rating: float
    timestamp: Optional[int] = None
    title: Optional[str] = None


class RecommendationResponse(BaseModel):
    user_id: str
    recommendations: list[Recommendation]
    past_ratings: list[PastRating]
    server_time_ms: float


class SampleUsers(BaseModel):
    user_ids: list[str]


# ---------- endpoints ----------
@app.get("/health")
def health():
    return {"status": "ok", "data_source": app.state.repo.name}


@app.get("/api/users/sample", response_model=SampleUsers)
def sample_users(limit: int = Query(5, ge=1, le=20)):
    return {"user_ids": app.state.repo.sample_user_ids(limit)}


@app.get("/api/users/{user_id}/recommendations", response_model=RecommendationResponse)
def user_recommendations(user_id: str, limit: int = Query(10, ge=1, le=10)):
    start = time.perf_counter()
    repo = app.state.repo
    user = repo.get_user(user_id.strip())
    if not user:
        raise HTTPException(status_code=404, detail=f"No recommendations found for user {user_id}")

    recs = sorted(user.get("recommendations", []), key=lambda r: r["rank"])[:limit]
    past = user.get("past_ratings", [])[:10]
    products = repo.get_products([r["product_id"] for r in recs] + [p["product_id"] for p in past])

    def details(pid):
        return products.get(pid, {})

    return {
        "user_id": user["_id"],
        "recommendations": [
            {**r, "title": details(r["product_id"]).get("title"),
             "price": details(r["product_id"]).get("price"),
             "average_rating": details(r["product_id"]).get("average_rating")}
            for r in recs
        ],
        "past_ratings": [{**p, "title": details(p["product_id"]).get("title")} for p in past],
        "server_time_ms": round((time.perf_counter() - start) * 1000, 2),
    }
