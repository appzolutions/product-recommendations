"""Copy the sample data into MongoDB Atlas, to test the connection before the real data is ready.

Usage:  python scripts/load_fixtures_to_mongo.py
Reads MONGODB_URI (and optional MONGODB_DB) from the .env file.
Writes to separate collections (products_sample, users_sample) unless you pass --replace-real,
so it never overwrites the real data written by the Spark notebook.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
uri = os.getenv("MONGODB_URI")
if not uri:
    sys.exit("Set MONGODB_URI in backend/.env first.")

folder = Path(__file__).resolve().parent.parent / "fixtures"
db = MongoClient(uri)[os.getenv("MONGODB_DB", "recommender")]
suffix = "" if "--replace-real" in sys.argv else "_sample"

for name in ["products", "users"]:
    docs = json.loads((folder / f"{name}.json").read_text())
    coll = db[name + suffix]
    coll.delete_many({})
    coll.insert_many(docs)
    print(f"Wrote {len(docs)} documents to {coll.name}")
