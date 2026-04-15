/// <reference types="node" />
import type { CapacitorConfig } from '@capacitor/cli'

// Set VITE_API_URL to your Railway URL before building for device.
// e.g.  $env:VITE_API_URL = "https://YOUR-APP.up.railway.app"
// Never commit a real URL here — use the env var.
const _rawUrl = process.env.VITE_API_URL ?? ''
if (!_rawUrl || _rawUrl.includes('your-app') || _rawUrl.includes('placeholder')) {
  // Fail the Capacitor config step loudly during `cap sync` rather than
  // silently shipping an APK that points at nothing.
  throw new Error(
    '[capacitor.config.ts] VITE_API_URL is not set.\n' +
    'Run:  $env:VITE_API_URL = "https://YOUR-APP.up.railway.app"  then retry.'
  )
}
const RAILWAY_URL = _rawUrl

const config: CapacitorConfig = {
  appId: 'com.akhi2026.cricinsightsai',
  appName: 'Cricket Insights AI',
  webDir: 'dist',
  server: {
    // On device, point directly at Railway backend
    url: RAILWAY_URL,
    cleartext: false,
  },
  android: {
    backgroundColor: '#0f172a',
  },
  ios: {
    backgroundColor: '#0f172a',
    contentInset: 'always',
    // Required for older Xcode/iOS: allow mixed content from Railway HTTPS
    allowsLinkPreview: false,
  },  plugins: {},
}

export default config
