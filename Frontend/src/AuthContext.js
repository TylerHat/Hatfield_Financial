import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiFetch } from './api';

const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('hf_token'));
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    console.log('[Auth] logout() — clearing token and user');
    localStorage.removeItem('hf_token');
    localStorage.removeItem('hf_user');
    setToken(null);
    setUser(null);
  }, []);

  // Validate token on mount
  useEffect(() => {
    if (!token) {
      console.log('[Auth] No token in localStorage — skipping /me validation');
      setLoading(false);
      return;
    }

    console.log('[Auth] Token found — validating via /api/auth/me');
    apiFetch('/api/auth/me')
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error(`Invalid token (status=${res.status})`);
      })
      .then((data) => {
        console.log('[Auth] Token validated. user=', data.user && data.user.username);
        setUser(data.user);
      })
      .catch((err) => {
        console.warn('[Auth] Token validation failed — logging out:', err.message);
        logout();
      })
      .finally(() => {
        setLoading(false);
      });
  }, [token, logout]);

  // Listen for 401 events from apiFetch
  useEffect(() => {
    const handleExpired = () => {
      console.warn('[Auth] hf_auth_expired event received — clearing session state');
      setToken(null);
      setUser(null);
    };
    window.addEventListener('hf_auth_expired', handleExpired);
    return () => window.removeEventListener('hf_auth_expired', handleExpired);
  }, []);

  const login = async (username, password) => {
    console.log('[Auth] login() attempt for user=', username);
    try {
      const res = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        console.warn('[Auth] login() failed:', res.status, data.error);
        throw new Error(data.error || 'Login failed');
      }
      console.log('[Auth] login() success — user=', data.user && data.user.username);
      localStorage.setItem('hf_token', data.token);
      localStorage.setItem('hf_user', JSON.stringify(data.user));
      setToken(data.token);
      setUser(data.user);
      return data;
    } catch (err) {
      console.error('[Auth] login() threw:', err.message);
      throw err;
    }
  };

  const register = async (username, password) => {
    console.log('[Auth] register() attempt for user=', username);
    try {
      const res = await apiFetch('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        console.warn('[Auth] register() failed:', res.status, data.error);
        throw new Error(data.error || 'Registration failed');
      }
      console.log('[Auth] register() success — user=', data.user && data.user.username);
      localStorage.setItem('hf_token', data.token);
      localStorage.setItem('hf_user', JSON.stringify(data.user));
      setToken(data.token);
      setUser(data.user);
      return data;
    } catch (err) {
      console.error('[Auth] register() threw:', err.message);
      throw err;
    }
  };

  const value = { user, token, loading, login, register, logout };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
