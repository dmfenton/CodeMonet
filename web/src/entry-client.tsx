/**
 * Client-side entry point for SSR hydration.
 * This file hydrates the server-rendered HTML with React.
 */

import { StrictMode } from 'react';
import { hydrateRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { HelmetProvider } from 'react-helmet-async';
import { AuthProvider } from './context/AuthContext';
import { AppRoutes } from './routes';
import './styles.css';
import './homepage.css';
import './components/AuthScreen.css';

// Get initial data injected by SSR
declare global {
  interface Window {
    __INITIAL_DATA__?: unknown;
  }
}

const initialData = window.__INITIAL_DATA__;

hydrateRoot(
  document.getElementById('root')!,
  <StrictMode>
    <HelmetProvider>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes initialData={initialData} />
        </AuthProvider>
      </BrowserRouter>
    </HelmetProvider>
  </StrictMode>
);
