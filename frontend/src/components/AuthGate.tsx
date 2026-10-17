/**
 * Authentication gate for the operations console.
 *
 * Renders a login form until an operator is authenticated, then renders the
 * console. Listens for forced-logout (token rejected) events and returns to the
 * login screen. The console UI itself is unchanged and only mounts when signed in.
 */

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  fetchCurrentOperatorApi,
  loginApi,
  logout as logoutApi,
  onUnauthorized,
  type OperatorIdentity,
} from '../api/authApi';

interface AuthGateProps {
  children: (operator: OperatorIdentity, onLogout: () => void) => ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const [operator, setOperator] = useState<OperatorIdentity | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;
    fetchCurrentOperatorApi()
      .then((op) => {
        if (active) setOperator(op);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    return onUnauthorized(() => setOperator(null));
  }, []);

  const handleLogout = useCallback(() => {
    logoutApi();
    setOperator(null);
  }, []);

  if (checking) {
    return (
      <div className="auth-screen" role="status" aria-live="polite">
        <p style={{ color: '#9fb0c3' }}>Verifying session…</p>
      </div>
    );
  }

  if (!operator) {
    return <LoginForm onAuthenticated={setOperator} />;
  }

  return <>{children(operator, handleLogout)}</>;
}

function LoginForm({ onAuthenticated }: { onAuthenticated: (op: OperatorIdentity) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      setError(null);
      setSubmitting(true);
      try {
        const op = await loginApi(username.trim(), password);
        onAuthenticated(op);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Login failed.');
      } finally {
        setSubmitting(false);
      }
    },
    [username, password, onAuthenticated]
  );

  return (
    <div
      className="auth-screen"
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0b111a',
        padding: 16,
      }}
    >
      <form
        onSubmit={handleSubmit}
        aria-label="Operator sign in"
        style={{
          width: '100%',
          maxWidth: 360,
          background: '#131c28',
          border: '1px solid #243244',
          borderRadius: 12,
          padding: 24,
          boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
        }}
      >
        <h1 style={{ color: '#e8eef5', fontSize: 20, margin: '0 0 4px' }}>AegisPay AI</h1>
        <p style={{ color: '#9fb0c3', fontSize: 13, margin: '0 0 20px' }}>
          Fraud Operations Console — operator sign in
        </p>

        <label htmlFor="login-username" style={labelStyle}>
          Username
        </label>
        <input
          id="login-username"
          name="username"
          type="text"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          style={inputStyle}
        />

        <label htmlFor="login-password" style={labelStyle}>
          Password
        </label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          style={inputStyle}
        />

        {error && (
          <p role="alert" style={{ color: '#ff8c8c', fontSize: 13, margin: '0 0 12px' }}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !username || !password}
          style={{
            width: '100%',
            padding: '10px 14px',
            borderRadius: 8,
            border: 'none',
            background: submitting ? '#2a6f97' : '#2f80c2',
            color: '#fff',
            fontSize: 14,
            fontWeight: 600,
            cursor: submitting ? 'default' : 'pointer',
          }}
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  color: '#c3d0de',
  fontSize: 12,
  fontWeight: 600,
  margin: '0 0 6px',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '9px 12px',
  marginBottom: 16,
  borderRadius: 8,
  border: '1px solid #2c3b4e',
  background: '#0e1621',
  color: '#e8eef5',
  fontSize: 14,
};
