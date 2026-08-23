import React, { StrictMode, useEffect, useRef, useState } from 'react';
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
  const callbackHandled = useRef(false);
  const { isLoading, isAuthenticated, exchangeAuthorizationCode } = useAuth();

  // Handle browser back/forward navigation
  useEffect(() => {
    const handlePopState = (): void => {
      setCurrentPath(window.location.pathname);
    };
    window.addEventListener('popstate', handlePopState);
    return (): void => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Handle platform authorization callback.
  useEffect(() => {
    if (currentPath === '/auth/callback') {
      if (callbackHandled.current) return;
      callbackHandled.current = true;
      const code = new URLSearchParams(window.location.search).get('code');
      if (!code) {
        setCallbackError('Invalid callback URL - missing authorization code');
        return;
      }
      void exchangeAuthorizationCode(code).then((result) => {
        if (result.success) {
          window.history.replaceState({}, '', '/studio');
          setCurrentPath('/studio');
        } else setCallbackError(result.error || 'Authentication failed');
      });
    }
  }, [currentPath, exchangeAuthorizationCode]);

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
