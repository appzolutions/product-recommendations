"""Upload the JSON files exported from Databricks into MongoDB Atlas.

Usage (from the backend folder, with MONGODB_URI in .env):
    python scripts/import_spark_output.py --users path/to/users --products path/to/products
    python scripts/import_spark_output.py --users ... --products ... --dry-run   # check the files only

Each path can be a single .json file or the folder Spark writes (it contains part-*.json files).
Files must be JSON Lines (one JSON object per line), which is what Spark's df.write.json() produces.
See api_contract.md, section 3, for the exact fields.

The script:
1. reads and checks every line (missing fields, wrong types, products that don't exist),
2. shows a summary and the estimated size (the free Atlas cluster holds 0.5 GB),
3. replaces the `products` and `users` collections with the new data (unless --dry-run).
"""
import argparse
import json
import os
import sys
from pathlib import Path

FREE_TIER_BYTES = 512 * 1024 * 1024


def read_json_lines(path_str):
    path = Path(path_str)
    if not path.exists():
        sys.exit(f"Not found: {path}")
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    files = [f for f in files if not f.name.startswith(("_", "."))]   # skip Spark's _SUCCESS etc.
    if not files:
        sys.exit(f"No .json files in {path}")
    docs = []
    for f in files:
        with f.open(encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    docs.append(json.loads(line))
                except json.JSONDecodeError as e:
                    sys.exit(f"{f.name}, line {n}: not valid JSON ({e}). Files must have one JSON object per line.")
    return docs


def check_products(docs):
    errors, clean = [], []
    for i, d in enumerate(docs, 1):
        if not d.get("_id"):
            errors.append(f"product #{i}: missing _id (the parent_asin)")
            continue
        clean.append({
            "_id": str(d["_id"]),
            "title": d.get("title"),
            "main_category": d.get("main_category"),
            "price": float(d["price"]) if d.get("price") not in (None, "", "None") else None,
            "average_rating": float(d["average_rating"]) if d.get("average_rating") is not None else None,
            "rating_number": int(d["rating_number"]) if d.get("rating_number") is not None else None,
        })
    return clean, errors


def check_users(docs, product_ids):
    errors, clean, unknown_products = [], [], set()
    for i, d in enumerate(docs, 1):
        uid = d.get("_id")
        recs = d.get("recommendations")
        if not uid:
            errors.append(f"user #{i}: missing _id (the Amazon user_id)")
            continue
        if not isinstance(recs, list) or not recs:
            errors.append(f"user {uid}: no recommendations list")
            continue
        try:
            recs = sorted(
                [{"rank": int(r["rank"]), "product_id": str(r["product_id"]),
                  "predicted_rating": round(float(r["predicted_rating"]), 2)} for r in recs],
                key=lambda r: r["rank"])
            past = [{"product_id": str(p["product_id"]), "rating": float(p["rating"]),
                     "timestamp": int(p["timestamp"]) if p.get("timestamp") is not None else None}
                    for p in (d.get("past_ratings") or [])]
        except (KeyError, TypeError, ValueError) as e:
            errors.append(f"user {uid}: a recommendation or past rating is missing a field or has a wrong type ({e})")
            continue
        for pid in [r["product_id"] for r in recs] + [p["product_id"] for p in past]:
            if pid not in product_ids:
                unknown_products.add(pid)
        clean.append({"_id": str(uid), "recommendations": recs, "past_ratings": past[:10]})
    return clean, errors, unknown_products


def approx_size(docs):
    return sum(len(json.dumps(d)) for d in docs)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", required=True, help="users export (file or Spark output folder)")
    parser.add_argument("--products", required=True, help="products export (file or Spark output folder)")
    parser.add_argument("--dry-run", action="store_true", help="check the files without uploading")
    args = parser.parse_args()

    products, p_errors = check_products(read_json_lines(args.products))
    users, u_errors, unknown = check_users(read_json_lines(args.users), {p["_id"] for p in products})

    print(f"Products: {len(products):,}   Users: {len(users):,}")
    size = approx_size(products) + approx_size(users)
    print(f"Estimated size: {size / 1024 / 1024:,.1f} MB (free Atlas limit: 512 MB, indexes need extra room)")
    if size > FREE_TIER_BYTES * 0.8:
        print("WARNING: close to or over the free limit. Ask for fewer users (for example, a higher minimum number of ratings).")
    if unknown:
        print(f"Note: {len(unknown):,} product IDs used in users are not in the products file "
              f"(those items will show their ID instead of a title). Example: {sorted(unknown)[:3]}")
    errors = p_errors + u_errors
    if errors:
        print(f"\n{len(errors)} problem(s) found:")
        for e in errors[:15]:
            print("  -", e)
        if len(errors) > 15:
            print(f"  ... and {len(errors) - 15} more")
        sys.exit("Nothing was uploaded. Fix the export (see api_contract.md, section 3) and try again.")

    if args.dry_run:
        print("\nDry run: the files look good. Run again without --dry-run to upload.")
        return

    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        sys.exit("Set MONGODB_URI in backend/.env first.")
    db = MongoClient(uri, serverSelectionTimeoutMS=10000)[os.getenv("MONGODB_DB", "recommender")]

    for name, docs in [("products", products), ("users", users)]:
        coll = db[name]
        coll.delete_many({})
        for start in range(0, len(docs), 1000):          # upload in batches of 1,000
            coll.insert_many(docs[start:start + 1000], ordered=False)
        print(f"Uploaded {len(docs):,} documents to '{name}'")
    print("Done. Restart the back end; /health should say \"data_source\": \"mongodb\".")


if __name__ == "__main__":
    main()
