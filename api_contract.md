# API contract and MongoDB schema

**Owner:** App lead (API + UI). **Agree with:** Precompute + storage lead (role 3).

This document fixes the shape of the data in MongoDB and what the API returns, so the Spark notebooks and the web app can be built at the same time. If anything here needs to change, update this file first and tell the App lead.

## 1. MongoDB (Atlas)

Database name: `recommender`

### Collection `products` (one document per product, written once)

```json
{
  "_id": "B07JGVX9D6",
  "title": "Example Game (Nintendo Switch)",
  "main_category": "Video Games",
  "price": 49.99,
  "average_rating": 4.6,
  "rating_number": 1830
}
```

| Field | Type | From the dataset | Notes |
|---|---|---|---|
| `_id` | string | `parent_asin` | The original Amazon product ID, **not** the StringIndexer number |
| `title` | string | `title` | |
| `main_category` | string | `main_category` | |
| `price` | number or `null` | `price` | Many products have no price: store `null` |
| `average_rating` | number | `average_rating` | |
| `rating_number` | integer | `rating_number` | Number of ratings on Amazon |

### Collection `users` (one document per user)

```json
{
  "_id": "AGBFYI2DDIKXC5Y4FARTYDTQBMFQ",
  "recommendations": [
    { "rank": 1, "product_id": "B07JGVX9D6", "predicted_rating": 4.87 },
    { "rank": 2, "product_id": "B0B1Z3H8VK", "predicted_rating": 4.71 }
  ],
  "past_ratings": [
    { "product_id": "B01N1037CV", "rating": 5.0, "timestamp": 1588615855070 }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `_id` | string | Original Amazon `user_id`, **not** the StringIndexer number |
| `recommendations` | array of 10 | From `recommendForAllUsers(10)`, sorted best first. `rank` starts at 1 |
| `recommendations[].product_id` | string | Original `parent_asin` (convert back from the ALS index) |
| `recommendations[].predicted_rating` | number | The ALS score, rounded to 2 decimals |
| `past_ratings` | array, up to 10 | The user's real ratings, newest first |
| `past_ratings[].timestamp` | integer | Milliseconds since 1970, as in the dataset |

**Storage limit (free Atlas cluster = 0.5 GB):** only write users with 5 or more ratings, and keep product details only in `products`, never copied into `users`.

**Important for the Spark side:** ALS works with the *numbers* created by StringIndexer. Before writing to MongoDB, convert them back to the original `user_id` and `parent_asin` (for example with `IndexToString`, or by joining with the indexer's lookup table).

## 2. API (FastAPI)

Base URL locally: `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.

### `GET /health`
Checks the API is running and shows where it reads data from.
```json
{ "status": "ok", "data_source": "mongodb" }
```
`data_source` is `"fixtures"` (sample JSON files) or `"mongodb"` (Atlas).

### `GET /api/users/sample?limit=5`
Returns a few user IDs to try in the demo (Amazon user IDs are long and random).
```json
{ "user_ids": ["AGBFYI2DDIKXC5Y4FARTYDTQBMFQ", "AHV6QCNBJNSGLATP56JAWJ3C4G2A"] }
```
`limit`: 1–20, default 5.

### `GET /api/users/{user_id}/recommendations?limit=10`
A user's recommendations, with product details joined in, plus what they rated before.
```json
{
  "user_id": "AGBFYI2DDIKXC5Y4FARTYDTQBMFQ",
  "recommendations": [
    {
      "rank": 1,
      "product_id": "B07JGVX9D6",
      "predicted_rating": 4.87,
      "title": "Example Game (Nintendo Switch)",
      "price": 49.99,
      "average_rating": 4.6
    }
  ],
  "past_ratings": [
    { "product_id": "B01N1037CV", "rating": 5.0, "timestamp": 1588615855070, "title": "Another Game (PC)" }
  ],
  "server_time_ms": 4.2
}
```
- `limit`: 1–10, default 10.
- If a product is missing from `products`, its `title` is `null` (the page shows the product ID instead).
- `server_time_ms`: how long the API took to answer, measured on the server.
- Every response also has the header `X-Process-Time-Ms`.

**Errors**
| Status | When | Body |
|---|---|---|
| 404 | No document for this user ID | `{ "detail": "No recommendations found for user <id>" }` |
| 422 | `limit` out of range | FastAPI's standard validation message |
