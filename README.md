# Game Picks: product recommendation web app

The App lead's part of the group project: a web page where you enter an Amazon user ID and see the top 10 video games the ALS model recommends for that user, next to the games they rated before.

```
React page  ->  FastAPI back end  ->  MongoDB Atlas
(frontend/)     (backend/)            (filled by the Spark notebooks in Databricks)
```

Until the real data is in MongoDB, the back end uses **sample data** in `backend/fixtures/` (8 made-up users, 48 made-up games) in exactly the same shape. Switching to the real database is only a setting: `MONGODB_URI`.

| File | What it is |
|---|---|
| `api_contract.md` | The agreed MongoDB layout and API responses. **Share this with the Precompute + storage lead.** |
| `backend/app/main.py` | The API (endpoints) |
| `backend/app/repository.py` | Reads data from the sample files or from MongoDB |
| `backend/tests/test_api.py` | Automatic tests (run against sample data and a simulated MongoDB) |
| `backend/scripts/measure_latency.py` | Measures response time, for Objective 4 in the proposal |
| `backend/scripts/load_fixtures_to_mongo.py` | Copies the sample data into Atlas, to test the connection early |
| `frontend/` | The React page (Vite) |
| `render.yaml` | Settings to host both parts on Render for free |

## 1. Run it on your Mac

You need **Python 3.10+** and **Node.js 18+** (check with `python3 --version` and `node --version`; install Node from nodejs.org if needed).

**Terminal window 1: back end**
```
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Open http://localhost:8000/docs to see and try the API.

**Terminal window 2: front end**
```
cd frontend
cp .env.example .env
npm install
npm run dev
```
Open http://localhost:5173 and click a sample user.

## 2. Run the tests and the speed measurement
With the back end's virtual environment active (`source .venv/bin/activate`), in `backend/`:
```
pytest
python scripts/measure_latency.py
```
`pytest` should end with **14 passed**. The speed script prints the median and 95th-percentile response time, which you can paste into the report.

## 3. Connect to MongoDB Atlas
1. Get the connection string from whoever created the Atlas cluster (Atlas > Connect > Drivers). It looks like `mongodb+srv://user:password@cluster0.xxxx.mongodb.net/`.
2. Put it in `backend/.env`: `MONGODB_URI=mongodb+srv://...`
3. In Atlas > Network Access, allow your IP address (or `0.0.0.0/0` for the demo).
4. Restart the back end. http://localhost:8000/health should now say `"data_source": "mongodb"`.

**Before the real data exists**, you can test the connection with the sample data:
```
python scripts/load_fixtures_to_mongo.py --replace-real
```
This writes the sample users and games into the `products` and `users` collections. Only use `--replace-real` while those collections are still empty; once the Spark notebook has written the real data, run it without the flag (it then writes to `products_sample` and `users_sample` instead).

Never commit the `.env` file: it contains the database password. `.gitignore` already excludes it.

## 4. Host it for free on Render
1. Put this folder in a GitHub repository.
2. In Render: **New + > Blueprint**, pick the repository. It reads `render.yaml` and creates two services.
3. Fill in the three values it asks for:
   - `MONGODB_URI`: the Atlas connection string
   - `VITE_API_URL`: the back end's address, for example `https://game-picks-api.onrender.com`
   - `ALLOWED_ORIGINS`: the page's address, for example `https://game-picks.onrender.com`
4. In Atlas > Network Access, allow `0.0.0.0/0` (Render's free plan has no fixed IP address).

**Free plan reminder:** the back end sleeps after 15 minutes without visitors, and the first request then takes about a minute. Open the page a few minutes before the demo, and run `measure_latency.py` against the live address only after it has woken up.
