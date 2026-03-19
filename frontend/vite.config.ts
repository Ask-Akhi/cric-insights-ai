import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const _react = (react as any).default ?? react

export default defineConfig(({ mode }) => ({
  plugins: [_react()],
  // Capacitor's Android WebView loads files from the filesystem, so paths must
  // be relative. For the normal web build (Vite dev + Railway) keep base: '/'.
  base: mode === 'capacitor' ? './' : '/',
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Raise the warning threshold — 800 KB is fine for this app
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        // Split vendor bundles so Railway build doesn't choke on one huge chunk
        manualChunks: {
          'react-vendor':   ['react', 'react-dom'],
          'motion':         ['framer-motion'],
          'charts':         ['recharts'],
          'markdown':       ['react-markdown'],          'router':         ['react-router-dom'],
        },
      },
    },
  },
}))
