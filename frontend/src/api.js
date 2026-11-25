// All calls to the FastAPI back end live here (see api_contract.md).
const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function getJson(path) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`);
  } catch {
    throw new Error(
      `Can't reach the API at ${API_URL}. Check that the back end is running. If it's hosted on a free plan, it may be waking up: try again in a minute.`
    );
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `The API answered with status ${response.status}.`);
  }
  return body;
}

export function getSampleUsers(limit = 4) {
  return getJson(`/api/users/sample?limit=${limit}`);
}

export async function getRecommendations(userId) {
  const started = performance.now();
  const data = await getJson(`/api/users/${encodeURIComponent(userId)}/recommendations`);
  return { ...data, round_trip_ms: performance.now() - started };
}
