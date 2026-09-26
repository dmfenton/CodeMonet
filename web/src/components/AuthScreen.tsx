/**
 * Authentication Screen - Magic link only
 */

import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Icon } from './brand/Icon';
import { Wordmark } from './brand/BrandMark';
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
      <div className="auth-card">
        {onBack && (
          <button className="btn-link auth-back" onClick={onBack} type="button">
            <Icon name="left" /> Home
          </button>
        )}

        <div className="auth-header">
          <Wordmark size="lg" />
          <h1 className="auth-title">Enter the studio</h1>
          <p className="auth-subtitle">We&apos;ll email you a sign-in link.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="email" className="mono-label">
            email
          </label>
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

          {error && (
            <div className="auth-message is-error" role="alert">
              {error}
            </div>
          )}
          {success && (
            <div className="auth-message is-success" role="status">
              {success}
            </div>
          )}

          <button type="submit" className="btn btn-primary auth-submit" disabled={loading}>
            {loading ? <span className="spinner spinner-sm" /> : 'Send sign-in link'}
          </button>
        </form>

        <p className="auth-note">Sign-in is provided by the private Fenton identity service.</p>
      </div>
    </div>
  );
}
