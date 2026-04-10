import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { AuthProvider } from './AuthContext';

// ── Global diagnostics ──────────────────────────────────────────────────────
// Log boot info and hook global error streams so any crash / rejection is
// visible in the browser console for diagnosis.
console.log('[Boot] Hatfield Financial frontend starting', {
  userAgent: navigator.userAgent,
  online: navigator.onLine,
  href: window.location.href,
  env: process.env.NODE_ENV,
  apiUrl: process.env.REACT_APP_API_URL || '(default localhost:5000)',
});

window.addEventListener('error', (event) => {
  console.error('[Global] window.error:', {
    message: event.message,
    source: event.filename,
    line: event.lineno,
    col: event.colno,
    error: event.error,
  });
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('[Global] unhandledrejection:', event.reason);
});

window.addEventListener('online', () => {
  console.log('[Global] network: online');
});
window.addEventListener('offline', () => {
  console.warn('[Global] network: offline');
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <AuthProvider>
    <App />
  </AuthProvider>
);
