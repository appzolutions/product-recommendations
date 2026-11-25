import { useEffect, useState } from "react";
import { getRecommendations, getSampleUsers } from "./api.js";

const shortId = (id) => (id.length > 12 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id);
const formatPrice = (price) => (price == null ? "Price not listed" : `$${price.toFixed(2)}`);
const formatDate = (ms) =>
  ms ? new Date(ms).toLocaleDateString("en-CA", { year: "numeric", month: "short" }) : "";

// Predicted rating (1–5) drawn as a five-segment meter, filled to the exact score
function RatingMeter({ value }) {
  return (
    <div className="meter" role="img" aria-label={`Predicted rating ${value.toFixed(1)} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => {
        const fill = Math.max(0, Math.min(1, value - (n - 1)));
        return (
          <span key={n} className="meter-cell">
            <span className="meter-fill" style={{ width: `${fill * 100}%` }} />
          </span>
        );
      })}
      <span className="meter-value">{value.toFixed(1)}</span>
    </div>
  );
}

function Stars({ value }) {
  return (
    <span className="stars" aria-label={`Rated ${value} out of 5`}>
      {"★".repeat(Math.round(value))}
      <span className="stars-empty">{"★".repeat(5 - Math.round(value))}</span>
    </span>
  );
}

export default function App() {
  const [userId, setUserId] = useState("");
  const [samples, setSamples] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getSampleUsers()
      .then((data) => setSamples(data.user_ids))
      .catch(() => setSamples([]));
  }, []);

  async function load(id) {
    const clean = id.trim();
    if (!clean) {
      setError("Enter a user ID, or pick one of the sample users.");
      return;
    }
    setUserId(clean);
    setLoading(true);
    setError("");
    try {
      setResult(await getRecommendations(clean));
    } catch (e) {
      setResult(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="masthead">
        <h1>Game Picks</h1>
        <p className="lede">
          Personal video game recommendations, learned by Spark from millions of Amazon reviews.
        </p>
      </header>

      <form
        className="search"
        onSubmit={(e) => {
          e.preventDefault();
          load(userId);
        }}
      >
        <label htmlFor="user-id">Amazon user ID</label>
        <div className="search-row">
          <input
            id="user-id"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="e.g. AGBFYI2DDIKXC5Y4FARTYDTQBMFQ"
            autoComplete="off"
            spellCheck="false"
          />
          <button type="submit" disabled={loading}>
            {loading ? "Loading…" : "Show recommendations"}
          </button>
        </div>
        {samples.length > 0 && (
          <div className="samples">
            <span>Try a sample user:</span>
            {samples.map((id) => (
              <button type="button" key={id} className="sample" onClick={() => load(id)} title={id}>
                {shortId(id)}
              </button>
            ))}
          </div>
        )}
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {!result && !error && (
        <p className="empty">Pick a sample user above to see what the model recommends for them.</p>
      )}

      {result && (
        <main className="results" aria-live="polite">
          <aside className="history">
            <h2>Rated before</h2>
            <p className="hint">What this user actually rated on Amazon.</p>
            <ul>
              {result.past_ratings.map((p) => (
                <li key={p.product_id}>
                  <span className="history-title">{p.title || p.product_id}</span>
                  <span className="history-meta">
                    <Stars value={p.rating} />
                    <span>{formatDate(p.timestamp)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </aside>

          <section className="picks">
            <div className="picks-head">
              <div>
                <h2>Recommended for this user</h2>
                <p className="hint">Bars show how many stars the model predicts this user would give, out of 5.</p>
              </div>
              <p className="timing">
                Answered in {Math.round(result.round_trip_ms)} ms ({result.server_time_ms.toFixed(1)} ms on the
                server)
              </p>
            </div>
            <ol>
              {result.recommendations.map((r) => (
                <li key={r.product_id} className={r.rank === 1 ? "pick top" : "pick"}>
                  <span className="rank">{r.rank}</span>
                  <div className="pick-body">
                    <h3>{r.title || r.product_id}</h3>
                    <p className="pick-meta">
                      {formatPrice(r.price)}
                      {r.average_rating != null && <>, Amazon average {r.average_rating.toFixed(1)}</>}
                    </p>
                  </div>
                  <div className="pick-score">
                    <RatingMeter value={r.predicted_rating} />
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </main>
      )}

      <footer className="foot">
        Recommendations are pre-computed with Spark MLlib (ALS) and served from MongoDB.
      </footer>
    </div>
  );
}
