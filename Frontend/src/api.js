const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5000';

console.log('[API] Module loaded. API_BASE =', API_BASE);

// ── Client-side response cache (2-min TTL) ──────────────────────────────────
// Prevents redundant GET requests when switching tabs or re-rendering.
// Only caches GET requests (no body/options). POST/PUT/DELETE bypass cache.
const _cache = new Map();
const _CACHE_TTL = 120_000; // 2 minutes in ms
const _CACHE_MAX = 50;

// Cache hit/miss counters for observability
const _cacheStats = { hits: 0, misses: 0, sets: 0, evictions: 0, expired: 0 };

function _cacheGet(key) {
  const entry = _cache.get(key);
  if (entry) {
    const ageMs = Date.now() - entry.ts;
    if (ageMs < _CACHE_TTL) {
      _cacheStats.hits++;
      console.log(`[API:cache] HIT  ${key}  (age=${ageMs}ms, size=${_cache.size}/${_CACHE_MAX})`);
      return entry.response.clone();
    }
    _cacheStats.expired++;
    console.log(`[API:cache] EXPIRED ${key}  (age=${ageMs}ms)`);
    _cache.delete(key);
  }
  _cacheStats.misses++;
  return null;
}

function _cacheSet(key, response) {
  // Evict oldest entry if cache grows too large
  if (_cache.size >= _CACHE_MAX) {
    const oldest = _cache.keys().next().value;
    _cache.delete(oldest);
    _cacheStats.evictions++;
    console.warn(`[API:cache] EVICT ${oldest}  (cache full at ${_CACHE_MAX})`);
  }
  _cache.set(key, { response: response.clone(), ts: Date.now() });
  _cacheStats.sets++;
  console.log(`[API:cache] SET  ${key}  (size=${_cache.size}/${_CACHE_MAX})`);
}

/** Expose cache stats to the console for live diagnosis (window.hfCacheStats()). */
if (typeof window !== 'undefined') {
  window.hfCacheStats = () => {
    const stats = { ..._cacheStats, size: _cache.size, keys: [..._cache.keys()] };
    console.table(stats);
    return stats;
  };
  window.hfCacheClear = () => {
    const n = _cache.size;
    _cache.clear();
    console.log(`[API:cache] CLEARED ${n} entries`);
  };
}

// Monotonic request ID so logs for a single request can be correlated.
let _reqCounter = 0;

/**
 * Auth-aware fetch wrapper. Injects Bearer token from localStorage
 * and handles 401 responses by clearing the stored token.
 * GET requests are cached client-side for 2 minutes.
 */
export async function apiFetch(path, options = {}) {
  const reqId = ++_reqCounter;
  const t0 = performance.now();
  const token = localStorage.getItem('hf_token');

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const method = (options.method || 'GET').toUpperCase();
  const isGet = method === 'GET';
  const bodySize = options.body ? (typeof options.body === 'string' ? options.body.length : '?') : 0;

  console.log(
    `[API] #${reqId} → ${method} ${path}`,
    `  auth=${token ? 'bearer' : 'none'}`,
    bodySize ? `  body=${bodySize}B` : '',
  );

  if (isGet) {
    const cached = _cacheGet(path);
    if (cached) {
      console.log(`[API] #${reqId} ← (client cache) ${method} ${path}  (${(performance.now() - t0).toFixed(1)}ms)`);
      return cached;
    }
  }

  const MAX_RETRIES = 3;
  const RETRY_DELAY = 3000;
  let response;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } catch (err) {
      const dt = (performance.now() - t0).toFixed(1);
      console.error(`[API] #${reqId} ✖ Network error on ${method} ${path}  (${dt}ms)`, {
        name: err.name,
        message: err.message,
        apiBase: API_BASE,
        online: typeof navigator !== 'undefined' ? navigator.onLine : 'n/a',
      });
      throw err;
    }

    if (response.status === 429 && attempt < MAX_RETRIES) {
      console.warn(
        `[API] #${reqId} ⚠ 429 on ${method} ${path} — retrying in ${RETRY_DELAY / 1000}s (attempt ${attempt + 1}/${MAX_RETRIES})`
      );
      await new Promise((r) => setTimeout(r, RETRY_DELAY));
      continue;
    }
    break;
  }

  const dt = (performance.now() - t0).toFixed(1);
  const contentLength = response.headers.get('content-length');
  const meta = contentLength ? `  ${contentLength}B` : '';

  // Log level depends on status category
  if (response.status >= 500) {
    console.error(`[API] #${reqId} ← ${response.status} ${method} ${path}  (${dt}ms)${meta}  [server error]`);
  } else if (response.status >= 400) {
    console.warn(`[API] #${reqId} ← ${response.status} ${method} ${path}  (${dt}ms)${meta}  [client error]`);
  } else if (response.status === 202) {
    console.log(`[API] #${reqId} ← ${response.status} ${method} ${path}  (${dt}ms)${meta}  [loading/accepted]`);
  } else {
    console.log(`[API] #${reqId} ← ${response.status} ${method} ${path}  (${dt}ms)${meta}`);
  }

  if (response.status === 401 && token) {
    console.warn(`[API] #${reqId} ⚠ 401 on ${path} — clearing auth token and emitting hf_auth_expired`);
    localStorage.removeItem('hf_token');
    localStorage.removeItem('hf_user');
    window.dispatchEvent(new Event('hf_auth_expired'));
  }

  // Cache successful GET responses (200 only — skip 202 "loading" state)
  if (isGet && response.status === 200) {
    _cacheSet(path, response);
  }

  return response;
}

export { API_BASE };
