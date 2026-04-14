import React, { useState } from 'react';
import { useAuth } from '../AuthContext';
import './AccountPanel.css';

export default function AccountPanel() {
  const { user, updateProfile } = useAuth();
  const [email, setEmail] = useState(user?.email || '');
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await updateProfile({ email: email.trim() || null });
      setSuccess('Profile updated.');
      setTimeout(() => setSuccess(null), 4000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="account-panel">
      <h2>Account Settings</h2>
      <p className="account-panel__username">
        Signed in as <strong>{user?.username}</strong>
      </p>
      {success && <div className="account-flash account-flash--success">{success}</div>}
      {error && <div className="account-flash account-flash--error">{error}</div>}
      <form onSubmit={handleSubmit} className="account-form">
        <div className="account-field">
          <label htmlFor="account-email">
            Email <span className="account-field__optional">(optional)</span>
          </label>
          <input
            id="account-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
          <p className="account-field__hint">
            Used for account identification only. No verification emails are sent.
          </p>
        </div>
        <button type="submit" className="account-submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </form>
    </div>
  );
}
