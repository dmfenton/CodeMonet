import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const version = process.env.VERSION || 'dev';

// Same API_URL the SSR server reads (src/config.ts); lets a worktree run its
// backend on a non-default port.
const devApiUrl = process.env.API_URL || 'http://localhost:8000';

export default defineConfig(({ mode }) => ({
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
    // The pre-render bundle needs only its template, not the public assets.
    copyPublicDir: mode !== 'prerender',
    // The client build's entry; `--ssr src/prerender.ts` overrides it.
    rollupOptions: {
      input: {
        main: './index.html',
      },
      // The pre-render bundle runs with plain `node` next to no package.json.
      ...(mode === 'prerender' ? { output: { entryFileNames: 'prerender.mjs' } } : {}),
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
    // The pre-render bundle is self-contained (the server image has node but no
    // node_modules); the dev SSR server bundles only react-helmet-async.
    noExternal: mode === 'prerender' ? true : ['react-helmet-async'],
  },
}));
