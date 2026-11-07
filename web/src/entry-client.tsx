/**
 * Client-side entry point.
 * Hydrates pre-rendered (or dev server-rendered) markup; renders from scratch
 * when nginx served the bare SPA shell (any route that is not pre-rendered).
 */

import { StrictMode } from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { HelmetProvider } from 'react-helmet-async';
import { AuthProvider } from './context/AuthContext';
import { AppRoutes } from './routes';
import './styles.css';
import './site.css';
import './components/AuthScreen.css';

// Get initial data injected by SSR
declare global {
  interface Window {
    __INITIAL_DATA__?: unknown;
  }
}

const initialData = window.__INITIAL_DATA__;

const container = document.getElementById('root')!;
const app = (
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

if (container.firstElementChild) {
  hydrateRoot(container, app);
} else {
  createRoot(container).render(app);
}
