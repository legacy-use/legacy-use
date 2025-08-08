import react from '@vitejs/plugin-react-swc';
import { defineConfig } from 'vite';
import path from 'node:path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react({
      jsxImportSource: '@emotion/react',
      plugins: [['@swc/plugin-emotion', {}]],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './app'),
    },
  },
  build: {
    outDir: 'build',
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ['.local.legacy-use.com'],
    watch: {
      ignored: ['**/.venv/**', '**/.git/**', '**/server/**', '**/node_modules/**'],
    },
    proxy: {
      '/api': {
        target: `http://${process.env.VITE_PROXY_TARGET || 'localhost'}:8088`,
        ws: true,        
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            // Preserve the original host header for multi-tenant support
            proxyReq.setHeader('Host', req.headers.host);
          });
        },
      },
    },
  },
  // Fixes ambiguous behavior with initial loading of MUI and Emotion packages
  optimizeDeps: {
    include: [
      '@mui/material',
      '@mui/system',
      '@emotion/react',
      '@emotion/styled',
      '@emotion/cache',
    ],
  },
  // makes sure 'global' points to 'globalThis' -> fixed ambiguous initial load
  define: {
    global: 'globalThis',
  },
});
