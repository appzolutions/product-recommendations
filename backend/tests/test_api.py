"""Endpoint tests. Run from the backend folder:  pytest"""
import json
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

from app import main
from app.repository import FixtureRepository, MongoRepository

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
USERS = json.loads((FIXTURES / "users.json").read_text())
PRODUCTS = json.loads((FIXTURES / "products.json").read_text())
KNOWN_USER = USERS[0]["_id"]


def fixture_repo():
    return FixtureRepository()


def mongo_repo():
    """A fake in-memory MongoDB filled with the sample data, to test the MongoDB code path."""
    client = mongomock.MongoClient()
    client["recommender"].products.insert_many([dict(p) for p in PRODUCTS])
    client["recommender"].users.insert_many([dict(u) for u in USERS])
    return MongoRepository("mongodb://test", client=client)


@pytest.fixture(params=[fixture_repo, mongo_repo], ids=["fixtures", "mongodb"])
def client(request):
    main.app.state.repo = request.param()
    return TestClient(main.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_recommendations_shape_and_order(client):
    r = client.get(f"/api/users/{KNOWN_USER}/recommendations")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == KNOWN_USER
    assert len(body["recommendations"]) == 10
    assert [x["rank"] for x in body["recommendations"]] == list(range(1, 11))
    scores = [x["predicted_rating"] for x in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert all(x["title"] for x in body["recommendations"])      # product details were joined in
    assert len(body["past_ratings"]) >= 1
    assert body["server_time_ms"] >= 0
    assert "X-Process-Time-Ms" in r.headers


def test_limit(client):
    r = client.get(f"/api/users/{KNOWN_USER}/recommendations?limit=3")
    assert [x["rank"] for x in r.json()["recommendations"]] == [1, 2, 3]


def test_limit_out_of_range(client):
    assert client.get(f"/api/users/{KNOWN_USER}/recommendations?limit=0").status_code == 422
    assert client.get(f"/api/users/{KNOWN_USER}/recommendations?limit=11").status_code == 422


def test_unknown_user_returns_404(client):
    r = client.get("/api/users/NOT_A_REAL_USER/recommendations")
    assert r.status_code == 404
    assert "NOT_A_REAL_USER" in r.json()["detail"]


def test_missing_product_details_do_not_break(client):
    repo = main.app.state.repo
    original = repo.get_products
    repo.get_products = lambda ids: {}            # simulate products missing from the catalog
    try:
        r = client.get(f"/api/users/{KNOWN_USER}/recommendations")
        assert r.status_code == 200
        assert r.json()["recommendations"][0]["title"] is None
    finally:
        repo.get_products = original


def test_sample_users(client):
    r = client.get("/api/users/sample?limit=3")
    ids = r.json()["user_ids"]
    assert len(ids) == 3
    assert set(ids) <= {u["_id"] for u in USERS}
