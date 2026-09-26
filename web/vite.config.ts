import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const version = process.env.VERSION || 'dev';

// Same API_URL the SSR server reads (src/config.ts); lets a worktree run its
// backend on a non-default port.
const devApiUrl = process.env.API_URL || 'http://localhost:8000';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'html-version',
      transformIndexHtml(html) {
        return html.replace('</head>', `  <meta name="version" content="${version}">\n  </head>`);
      },
    },
  ],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  build: {
    // SSR builds need different entry points
    rollupOptions: {
      input: {
        main: './index.html',
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: devApiUrl,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: devApiUrl.replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
  // SSR configuration
  ssr: {
    // Dependencies that should be bundled for SSR
    noExternal: ['react-helmet-async'],
  },
});
