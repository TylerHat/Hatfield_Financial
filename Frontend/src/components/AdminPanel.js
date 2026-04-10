import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../AuthContext';
import { apiFetch } from '../api';
import './AdminPanel.css';

function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

function formatAge(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const days = Math.floor((now - d) / (1000 * 60 * 60 * 24));
  if (days < 1) return 'today';
  if (days === 1) return '1 day';
  if (days < 30) return `${days} days`;
  const months = Math.floor(days / 30);
  if (months < 12) return months === 1 ? '1 month' : `${months} months`;
  const years = Math.floor(days / 365);
  return years === 1 ? '1 year' : `${years} years`;
}

function DeleteConfirmModal({ user, onConfirm, onCancel, busy, error }) {
  const [typed, setTyped] = useState('');
  const canConfirm = typed === user.username && !busy;

  return (
    <div className="admin-modal-backdrop" onClick={onCancel}>
      <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Delete user?</h3>
        <p>
          This will permanently delete <strong>{user.username}</strong> and
          all of their watchlists, portfolio holdings, and settings. This
          action cannot be undone.
        </p>
        <p className="admin-modal__instructions">
          Type <code>{user.username}</code> to confirm:
        </p>
        <input
          type="text"
          className="admin-modal__input"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoFocus
          spellCheck={false}
          autoComplete="off"
        />
        {error && <div className="admin-modal__error">{error}</div>}
        <div className="admin-modal__actions">
          <button
            type="button"
            className="admin-btn admin-btn--cancel"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="admin-btn admin-btn--danger"
            onClick={onConfirm}
            disabled={!canConfirm}
          >
            {busy ? 'Deleting…' : 'Delete user'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminPanel() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [targetUser, setTargetUser] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const [flash, setFlash] = useState(null);

  const loadUsers = useCallback(async () => {
    console.log('[AdminPanel] loadUsers');
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch('/api/admin/users');
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to load users');
      }
      console.log(`[AdminPanel] loaded ${data.users?.length || 0} user(s)`);
      setUsers(data.users || []);
    } catch (err) {
      console.error('[AdminPanel] loadUsers failed:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  async function handleConfirmDelete() {
    if (!targetUser) return;
    console.warn('[AdminPanel] DELETE user', targetUser.id, targetUser.username);
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      const res = await apiFetch(`/api/admin/users/${targetUser.id}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to delete user');
      }
      console.log('[AdminPanel] user deleted successfully:', targetUser.username);
      setUsers((prev) => prev.filter((u) => u.id !== targetUser.id));
      setFlash(data.message || `User ${targetUser.username} deleted`);
      setTargetUser(null);
      setTimeout(() => setFlash(null), 4000);
    } catch (err) {
      console.error('[AdminPanel] delete failed:', err);
      setDeleteError(err.message);
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="admin-panel">
      <div className="admin-panel__header">
        <h2>Administration</h2>
        <p className="admin-panel__subtitle">
          Manage all registered users. Deleting a user cascades to their
          watchlists, portfolio, and settings.
        </p>
      </div>

      {flash && <div className="admin-flash admin-flash--success">{flash}</div>}
      {error && <div className="admin-flash admin-flash--error">{error}</div>}

      {loading ? (
        <div className="admin-loading">Loading users…</div>
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Member since</th>
                <th>Last login</th>
                <th className="admin-table__actions-col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="admin-table__empty">No users found.</td>
                </tr>
              )}
              {users.map((u) => {
                const isSelf = u.id === currentUser?.id;
                const deletable = !isSelf && !u.is_admin;
                return (
                  <tr key={u.id}>
                    <td className="admin-table__username">
                      {u.username}
                      {isSelf && <span className="admin-table__self-tag"> (you)</span>}
                    </td>
                    <td>
                      {u.is_admin ? (
                        <span className="admin-badge admin-badge--admin">Admin</span>
                      ) : (
                        <span className="admin-badge">User</span>
                      )}
                    </td>
                    <td>
                      <div>{formatDate(u.created_at)}</div>
                      <div className="admin-table__age">{formatAge(u.created_at)}</div>
                    </td>
                    <td>{formatDate(u.last_login_at)}</td>
                    <td className="admin-table__actions-col">
                      <button
                        type="button"
                        className="admin-btn admin-btn--danger admin-btn--small"
                        disabled={!deletable}
                        title={
                          isSelf
                            ? 'You cannot delete your own account'
                            : u.is_admin
                              ? 'Cannot delete another admin'
                              : 'Delete user'
                        }
                        onClick={() => {
                          setDeleteError(null);
                          setTargetUser(u);
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {targetUser && (
        <DeleteConfirmModal
          user={targetUser}
          onConfirm={handleConfirmDelete}
          onCancel={() => {
            if (!deleteBusy) {
              setTargetUser(null);
              setDeleteError(null);
            }
          }}
          busy={deleteBusy}
          error={deleteError}
        />
      )}
    </div>
  );
}
