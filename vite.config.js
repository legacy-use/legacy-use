import react from '@vitejs/plugin-react-swc';
import { defineConfig } from 'vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react({
      jsxImportSource: '@emotion/react',
      plugins: [['@swc/plugin-emotion', {}]],
    }),
  ],
  build: {
    outDir: 'build',
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      ignored: ['**/.venv/**', '**/.git/**', '**/server/**', '**/node_modules/**'],
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
