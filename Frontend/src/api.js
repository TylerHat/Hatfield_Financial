const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5000';

// ── Client-side response cache (2-min TTL) ──────────────────────────────────
// Prevents redundant GET requests when switching tabs or re-rendering.
// Only caches GET requests (no body/options). POST/PUT/DELETE bypass cache.
const _cache = new Map();
const _CACHE_TTL = 120_000; // 2 minutes in ms

function _cacheGet(key) {
  const entry = _cache.get(key);
  if (entry && Date.now() - entry.ts < _CACHE_TTL) {
    return entry.response.clone();
  }
  _cache.delete(key);
  return null;
}

function _cacheSet(key, response) {
  // Evict old entries if cache grows too large (max 50 entries)
  if (_cache.size >= 50) {
    const oldest = _cache.keys().next().value;
    _cache.delete(oldest);
  }
  _cache.set(key, { response: response.clone(), ts: Date.now() });
}

/**
 * Auth-aware fetch wrapper. Injects Bearer token from localStorage
 * and handles 401 responses by clearing the stored token.
 * GET requests are cached client-side for 2 minutes.
 */
export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('hf_token');

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Only cache GET requests (no method or method === 'GET')
  const method = (options.method || 'GET').toUpperCase();
  const isGet = method === 'GET';

  if (isGet) {
    const cached = _cacheGet(path);
    if (cached) return cached;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401 && token) {
    localStorage.removeItem('hf_token');
    localStorage.removeItem('hf_user');
    window.dispatchEvent(new Event('hf_auth_expired'));
  }

  // Cache successful GET responses
  if (isGet && response.ok) {
    _cacheSet(path, response);
  }

  return response;
}

export { API_BASE };
