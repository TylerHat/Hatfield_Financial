const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5000';

// ── Client-side response cache (2-min TTL) ──────────────────────────────────
// Prevents redundant GET requests when switching tabs or re-rendering.
// Only caches GET requests (no body/options). POST/PUT/DELETE bypass cache.
//
// Cache value stores the response BODY TEXT (not a cloned Response). Holding
// Response objects pins their body buffers in memory — at ~5-10 KB per JSON
// payload × 50 entries that's ~250-500 KB just to get streams nobody is
// reading. The body text is cheap to keep and re-wrap in a new Response on
// each hit.
//
// Eviction is LRU (touch on read): on each hit we delete + re-insert so the
// Map's insertion-order = recency-order, and eviction removes the
// least-recently-accessed key (Map.keys().next() returns oldest). The
// previous FIFO behavior would evict a hot key just because it was inserted
// first.
const _cache = new Map();
const _CACHE_TTL = 120_000; // 2 minutes in ms
const _CACHE_MAX_ENTRIES = 50;

function _cacheGet(key) {
  const entry = _cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts >= _CACHE_TTL) {
    _cache.delete(key);
    return null;
  }
  // Touch — move to end so LRU eviction picks the right victim.
  _cache.delete(key);
  _cache.set(key, entry);
  return new Response(entry.body, {
    status: 200,
    headers: { 'Content-Type': entry.contentType || 'application/json' },
  });
}

function _cacheSet(key, body, contentType) {
  if (_cache.size >= _CACHE_MAX_ENTRIES) {
    // Evict least-recently-accessed (oldest insertion = oldest access).
    const oldest = _cache.keys().next().value;
    _cache.delete(oldest);
  }
  _cache.set(key, { body, contentType, ts: Date.now() });
}

/**
 * Auth-aware fetch wrapper. Injects Bearer token from localStorage
 * and handles 401 responses by dispatching an auth-expired event for
 * AuthContext to consume (AuthContext is the single owner of token
 * storage; api.js does not touch localStorage directly).
 *
 * GET requests are cached client-side for 2 minutes by default. Pass
 * `{ skipCache: true }` to bypass for a specific call (e.g. polling).
 */
export async function apiFetch(path, options = {}) {
  const { skipCache = false, ...fetchOptions } = options;
  const token = localStorage.getItem('hf_token');

  const headers = {
    'Content-Type': 'application/json',
    ...fetchOptions.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Only cache GET requests (no method or method === 'GET')
  const method = (fetchOptions.method || 'GET').toUpperCase();
  const isGet = method === 'GET';

  if (isGet && !skipCache) {
    const cached = _cacheGet(path);
    if (cached) {
      console.log('[API] GET', path, '→ (client cache)');
      return cached;
    }
  }

  const MAX_RETRIES = 3;
  const RETRY_DELAY = 3000;
  let response;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers });
    } catch (err) {
      console.error('[API] Network error on', method, path, err);
      throw err;
    }

    if (response.status === 429 && attempt < MAX_RETRIES) {
      console.warn(`[API] 429 on ${method} ${path} — retrying in ${RETRY_DELAY / 1000}s (attempt ${attempt + 1}/${MAX_RETRIES})`);
      await new Promise(r => setTimeout(r, RETRY_DELAY));
      continue;
    }
    break;
  }

  console.log('[API]', method, path, '→', response.status);

  if (response.status === 401 && token) {
    console.warn('[API] 401 on', path, '— notifying AuthContext');
    // Pass the token that triggered the 401 so AuthContext can ignore the
    // event if the user has already re-authenticated with a different
    // token. This closes the race where a login that races a stale 401
    // would have its fresh token wiped.
    window.dispatchEvent(new CustomEvent('hf_auth_expired', { detail: { token } }));
  }

  // Cache successful GET responses (200 only — skip 202 "loading" state).
  // Buffer the body text once and stash it; the caller still gets a fresh
  // Response from this call, and future cache hits get a freshly-wrapped one.
  if (isGet && !skipCache && response.status === 200) {
    const contentType = response.headers.get('Content-Type') || 'application/json';
    const body = await response.clone().text();
    _cacheSet(path, body, contentType);
  }

  return response;
}

export { API_BASE };
