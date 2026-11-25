"""Where the API gets its data from.

Two interchangeable sources with the same methods:
- FixtureRepository: reads the sample JSON files in /fixtures (works with no database).
- MongoRepository: reads the real data from MongoDB Atlas.

main.py picks one based on the MONGODB_URI setting, so switching from sample data
to the real database is a configuration change, not a code change.
"""
import json
import random
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class FixtureRepository:
    name = "fixtures"

    def __init__(self, folder: Path = FIXTURES_DIR):
        products = json.loads((folder / "products.json").read_text())
        users = json.loads((folder / "users.json").read_text())
        self.products = {p["_id"]: p for p in products}
        self.users = {u["_id"]: u for u in users}

    def get_user(self, user_id: str):
        return self.users.get(user_id)

    def get_products(self, product_ids: list[str]) -> dict:
        return {pid: self.products[pid] for pid in product_ids if pid in self.products}

    def sample_user_ids(self, limit: int) -> list[str]:
        ids = list(self.users)
        return random.sample(ids, min(limit, len(ids)))


class MongoRepository:
    name = "mongodb"

    def __init__(self, uri: str, db_name: str = "recommender", client=None):
        if client is None:
            from pymongo import MongoClient
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = client[db_name]

    def get_user(self, user_id: str):
        return self.db.users.find_one({"_id": user_id})

    def get_products(self, product_ids: list[str]) -> dict:
        if not product_ids:
            return {}
        cursor = self.db.products.find({"_id": {"$in": product_ids}})   # one query for all products
        return {p["_id"]: p for p in cursor}

    def sample_user_ids(self, limit: int) -> list[str]:
        pipeline = [{"$sample": {"size": limit}}, {"$project": {"_id": 1}}]
        return [doc["_id"] for doc in self.db.users.aggregate(pipeline)]
