/**
 * Authentication Screen - Magic link only
 */

import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import './AuthScreen.css';

interface AuthScreenProps {
  onBack?: () => void;
}

export function AuthScreen({ onBack }: AuthScreenProps): React.ReactElement {
  const { requestMagicLink } = useAuth();

  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const clearMessages = (): void => {
    setError(null);
    setSuccess(null);
  };

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    clearMessages();
    setLoading(true);

    try {
      if (!email.trim()) {
        setError('Email is required');
        setLoading(false);
        return;
      }

      const result = await requestMagicLink(email);
      if (result.success) {
        setSuccess('Check your email for a sign-in link');
      } else {
        setError(result.error ?? 'Failed to send magic link');
      }
    } catch {
      setError('An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    setEmail(e.target.value);
    clearMessages();
  };

  return (
    <div className="auth-screen">
      <div className="auth-container">
        {onBack && (
          <button className="auth-back" onClick={onBack} type="button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Back to Home
          </button>
        )}

        <div className="auth-header">
          <div className="auth-logo">
            <svg viewBox="0 0 40 40">
              <circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path
                d="M 12 28 Q 20 10, 28 28"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <h1 className="auth-title">Code Monet</h1>
          <p className="auth-subtitle">Sign in with email</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="auth-field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={handleEmailChange}
              placeholder="you@example.com"
              autoComplete="email"
              disabled={loading}
              required
            />
          </div>

          {error && <div className="auth-error">{error}</div>}
          {success && <div className="auth-success">{success}</div>}

          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? (
              <span className="auth-spinner" />
            ) : (
              'Send Magic Link'
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p className="auth-note">
            Sign-in is provided by the private Fenton identity service.
          </p>
        </div>
      </div>
    </div>
  );
}
