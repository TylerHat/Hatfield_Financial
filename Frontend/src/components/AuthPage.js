import React, { useState } from 'react';
import { useAuth } from '../AuthContext';
import './AuthPage.css';

function AuthPage() {
  const { login, register } = useAuth();
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      if (isLogin) {
        await login(email, password);
      } else {
        await register(username, email, password);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleMode = () => {
    setIsLogin(!isLogin);
    setError('');
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <h1>Hatfield Investments</h1>
          <p>Financial Analytics Dashboard</p>
        </div>

        <h2 className="auth-title">{isLogin ? 'Sign In' : 'Create Account'}</h2>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          {!isLogin && (
            <div className="auth-field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="3-30 characters"
                autoComplete="username"
                required
              />
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
          </div>

          <div className="auth-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isLogin ? 'Enter password' : '8+ chars, upper, lower, digit'}
              autoComplete={isLogin ? 'current-password' : 'new-password'}
              required
            />
          </div>

          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting
              ? (isLogin ? 'Signing in...' : 'Creating account...')
              : (isLogin ? 'Sign In' : 'Create Account')}
          </button>
        </form>

        <div className="auth-toggle">
          {isLogin ? (
            <span>
              Don't have an account?{' '}
              <button type="button" onClick={toggleMode} className="auth-link">
                Create one
              </button>
            </span>
          ) : (
            <span>
              Already have an account?{' '}
              <button type="button" onClick={toggleMode} className="auth-link">
                Sign in
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuthPage;
