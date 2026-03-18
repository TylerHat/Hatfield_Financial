const API_BASE = 'http://localhost:5000';

/**
 * Auth-aware fetch wrapper. Injects Bearer token from localStorage
 * and handles 401 responses by clearing the stored token.
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

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401 && token) {
    localStorage.removeItem('hf_token');
    localStorage.removeItem('hf_user');
    window.dispatchEvent(new Event('hf_auth_expired'));
  }

  return response;
}

export { API_BASE };
