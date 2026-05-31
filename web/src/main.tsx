import React, { StrictMode, useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { Homepage } from './components/Homepage';
import { AuthScreen } from './components/AuthScreen';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RendererProvider } from './context/RendererContext';
import './styles.css';
import './homepage.css';
import './components/AuthScreen.css';

function Router(): React.ReactElement {
  const [currentPath, setCurrentPath] = useState(() => window.location.pathname);
  const [callbackError, setCallbackError] = useState<string | null>(null);
  const { isLoading, isAuthenticated, setTokensFromCallback } = useAuth();

  // Handle browser back/forward navigation
  useEffect(() => {
    const handlePopState = (): void => {
      setCurrentPath(window.location.pathname);
    };
    window.addEventListener('popstate', handlePopState);
    return (): void => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Handle magic link callback - extract tokens from URL fragment
  useEffect(() => {
    if (currentPath === '/auth/callback') {
      const hash = window.location.hash.substring(1); // Remove leading #
      const params = new URLSearchParams(hash);
      const accessToken = params.get('access_token');
      const refreshToken = params.get('refresh_token');

      if (accessToken && refreshToken) {
        const result = setTokensFromCallback(accessToken, refreshToken);
        if (result.success) {
          // Clear the hash and redirect to studio
          window.history.replaceState({}, '', '/studio');
          setCurrentPath('/studio');
        } else {
          setCallbackError(result.error || 'Authentication failed');
        }
      } else {
        setCallbackError('Invalid callback URL - missing tokens');
      }
    }
  }, [currentPath, setTokensFromCallback]);

  const navigateTo = (path: string): void => {
    window.history.pushState({}, '', path);
    setCurrentPath(path);
  };

  const handleEnterStudio = (): void => {
    navigateTo('/studio');
  };

  const handleBackToHome = (): void => {
    navigateTo('/');
  };

  // Handle auth callback route
  if (currentPath === '/auth/callback') {
    return (
      <div className="auth-loading">
        {callbackError ? (
          <div className="auth-error">
            <p>{callbackError}</p>
            <button onClick={handleBackToHome}>Back to Home</button>
          </div>
        ) : (
          <div className="auth-spinner" />
        )}
      </div>
    );
  }

  // Show loading while checking auth
  if (currentPath === '/studio' && isLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" />
      </div>
    );
  }

  // Studio requires authentication
  if (currentPath === '/studio') {
    if (!isAuthenticated) {
      return <AuthScreen onBack={handleBackToHome} />;
    }
    return <App />;
  }

  // Homepage is public
  return <Homepage onEnter={handleEnterStudio} />;
}

function Root(): React.ReactElement {
  return (
    <RendererProvider>
      <AuthProvider>
        <Router />
      </AuthProvider>
    </RendererProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>
);
