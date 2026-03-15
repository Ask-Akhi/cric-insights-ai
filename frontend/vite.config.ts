import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const _react = (react as any).default ?? react

export default defineConfig({
  plugins: [_react()],
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
          'markdown':       ['react-markdown'],
          'router':         ['react-router-dom'],
        },
      },
    },
  },
})
