"""Turn the team's Databricks outputs, as they are, into the two files the app needs.

You give it:
  --reviews  the `reviews_indexed` folder from the shared Volume (Parquet)
             (it already holds both the Amazon IDs and the ALS numbers, so no mapping tables are needed)
  --recs     the ALS output, saved in whatever shape the model produced (Parquet or JSON folder):
               a) straight from recommendForAllUsers(N):  user_idx, recommendations[ {product_idx, rating} ]
               b) or a flat table:                       user_idx, product_idx, rating|prediction
  --meta     meta_Video_Games.jsonl.gz, the Amazon product file (titles, prices, images).
             It is already in the shared Volume: /Volumes/workspace/default/video_games_raw/meta_Video_Games.jsonl.gz
             (or download it: https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/meta_categories/meta_Video_Games.jsonl.gz)

It writes (to --out, default ./app_data):
  users.jsonl     one line per user: top 10 recommendations (already-rated games removed) + last 10 ratings
  products.jsonl  one line per product used: title, category, price, ratings, image

Then upload them with:
  python scripts/import_spark_output.py --users app_data/users.jsonl --products app_data/products.jsonl

Example:
  python scripts/build_from_databricks.py --reviews downloads/reviews_indexed --recs downloads/als_recs \
         --meta downloads/meta_Video_Games.jsonl.gz
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------- reading
def read_table(path_str, columns=None):
    """Read a Spark output folder (part-*.parquet / part-*.json) or a single file."""
    path = Path(path_str)
    if not path.exists():
        sys.exit(f"Not found: {path}")
    files = sorted(path.iterdir()) if path.is_dir() else [path]
    files = [f for f in files if f.is_file() and not f.name.startswith(("_", "."))]
    parquet = [f for f in files if f.suffix == ".parquet" or ".parquet" in f.name]
    jsons = [f for f in files if f.suffix in (".json", ".jsonl") or f.name.endswith((".json.gz", ".jsonl.gz"))]
    if parquet:
        return pd.concat([pd.read_parquet(f, columns=columns) for f in parquet], ignore_index=True)
    if jsons:
        df = pd.concat([pd.read_json(f, lines=True) for f in jsons], ignore_index=True)
        return df[columns] if columns else df
    sys.exit(f"No Parquet or JSON files found in {path}")


def flatten_recs(recs):
    """Accept the nested recommendForAllUsers shape or an already flat table."""
    if "recommendations" in recs.columns:
        flat = recs[["user_idx", "recommendations"]].explode("recommendations").dropna(subset=["recommendations"])
        items = pd.DataFrame(flat["recommendations"].tolist(), index=flat.index)
        score_col = next(c for c in ["rating", "prediction", "predicted_rating"] if c in items.columns)
        return pd.DataFrame({"user_idx": flat["user_idx"].astype("int64").values,
                             "product_idx": items["product_idx"].astype("int64").values,
                             "score": items[score_col].astype(float).values})
    score_col = next((c for c in ["prediction", "predicted_rating", "rating", "score"] if c in recs.columns), None)
    if score_col is None or "product_idx" not in recs.columns:
        sys.exit("The ALS file needs either a 'recommendations' column, or columns user_idx, product_idx and a score "
                 f"(prediction/rating). Found: {list(recs.columns)}")
    return pd.DataFrame({"user_idx": recs["user_idx"].astype("int64"),
                         "product_idx": recs["product_idx"].astype("int64"),
                         "score": recs[score_col].astype(float)})


def first_image(images):
    if isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                url = img.get("large") or img.get("thumb") or img.get("hi_res")
                if url:
                    return url
    return None


def to_float(value):
    try:
        return float(value) if value not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def read_meta(meta_path, wanted_ids):
    """Stream the (large) Amazon metadata file and keep only the products we use."""
    opener = gzip.open if str(meta_path).endswith(".gz") else open
    found = {}
    with opener(meta_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            pid = item.get("parent_asin")
            if pid in wanted_ids and pid not in found:
                found[pid] = {
                    "title": item.get("title") or None,
                    "main_category": item.get("main_category") or None,
                    "price": to_float(item.get("price")),
                    "average_rating": to_float(item.get("average_rating")),
                    "rating_number": int(item["rating_number"]) if item.get("rating_number") is not None else None,
                    "image": first_image(item.get("images")),
                }
    return found


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reviews", required=True, help="reviews_indexed folder (Parquet)")
    ap.add_argument("--recs", required=True, help="ALS output folder or file (Parquet or JSON)")
    ap.add_argument("--meta", help="meta_Video_Games.jsonl.gz (titles, prices, images)")
    ap.add_argument("--out", default="app_data", help="output folder (default: app_data)")
    ap.add_argument("--top", type=int, default=10, help="recommendations per user (default 10)")
    ap.add_argument("--max-past", type=int, default=10, help="past ratings stored per user (default 10)")
    ap.add_argument("--min-ratings", type=int, default=0,
                    help="only store users with at least this many ratings (to save database space)")
    args = ap.parse_args()

    print("Reading reviews_indexed...")
    reviews = read_table(args.reviews, ["user_id", "parent_asin", "user_idx", "product_idx", "rating", "timestamp"])
    user_ids = reviews[["user_idx", "user_id"]].drop_duplicates("user_idx")
    product_ids = reviews[["product_idx", "parent_asin"]].drop_duplicates("product_idx")
    print(f"  {len(reviews):,} ratings, {len(user_ids):,} users, {len(product_ids):,} products")

    print("Reading the ALS output...")
    recs = flatten_recs(read_table(args.recs))
    per_user_in = recs.groupby("user_idx").size().max()
    print(f"  {recs['user_idx'].nunique():,} users with up to {per_user_in} recommendations each")

    # remove games the user has already rated (ALS does not do this by itself)
    rated = reviews[["user_idx", "product_idx"]].assign(_rated=True)
    recs = recs.merge(rated, on=["user_idx", "product_idx"], how="left")
    removed = int(recs["_rated"].fillna(False).astype(bool).sum())
    recs = recs[recs["_rated"].isna()].drop(columns="_rated")
    print(f"  removed {removed:,} recommendations of games the user had already rated")

    if args.min_ratings:
        counts = reviews.groupby("user_idx").size()
        keep = counts[counts >= args.min_ratings].index
        recs = recs[recs["user_idx"].isin(keep)]
        print(f"  keeping users with {args.min_ratings}+ ratings: {recs['user_idx'].nunique():,} users")

    # rank best first, keep the top N, translate numbers back to Amazon IDs
    recs = recs.sort_values(["user_idx", "score"], ascending=[True, False])
    recs["rank"] = recs.groupby("user_idx").cumcount() + 1
    recs = recs[recs["rank"] <= args.top]
    recs = recs.merge(user_ids, on="user_idx").merge(product_ids, on="product_idx")
    short = (recs.groupby("user_idx").size() < args.top).sum()
    if short:
        print(f"  note: {short:,} users have fewer than {args.top} recommendations after removing already-rated games "
              f"(ask for more, e.g. recommendForAllUsers({args.top * 2}), to avoid this)")

    # last ratings for each stored user, newest first
    stored_users = set(recs["user_idx"].unique())
    past = reviews[reviews["user_idx"].isin(stored_users)].sort_values(["user_idx", "timestamp"], ascending=[True, False])
    past = past[past.groupby("user_idx").cumcount() < args.max_past]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("Writing users.jsonl...")
    past_by_user = {
        u: [{"product_id": r.parent_asin, "rating": float(r.rating),
             "timestamp": int(r.timestamp) if pd.notna(r.timestamp) else None}
            for r in g.itertuples(index=False)]
        for u, g in past.groupby("user_idx")
    }
    n_users = 0
    with (out / "users.jsonl").open("w", encoding="utf-8") as fh:
        for u, g in recs.groupby("user_idx"):
            doc = {"_id": g["user_id"].iloc[0],
                   "recommendations": [{"rank": int(r.rank), "product_id": r.parent_asin,
                                        "predicted_rating": round(float(r.score), 2)}
                                       for r in g.itertuples(index=False)],
                   "past_ratings": past_by_user.get(u, [])}
            fh.write(json.dumps(doc) + "\n")
            n_users += 1

    print("Writing products.jsonl...")
    used = set(recs["parent_asin"]) | set(past["parent_asin"])
    meta = {}
    if args.meta:
        print("  reading product details from the Amazon metadata file (this can take a minute)...")
        meta = read_meta(args.meta, used)
        print(f"  found details for {len(meta):,} of {len(used):,} products")
    else:
        print("  no --meta file given: products will have no title or price (the app shows their ID instead)")
    with (out / "products.jsonl").open("w", encoding="utf-8") as fh:
        for pid in sorted(used):
            fh.write(json.dumps({"_id": pid, **meta.get(pid, {})}) + "\n")

    print(f"\nDone: {n_users:,} users and {len(used):,} products written to {out}/")
    print(f"Next: python scripts/import_spark_output.py --users {out}/users.jsonl --products {out}/products.jsonl --dry-run")


if __name__ == "__main__":
    main()
