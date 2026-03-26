import type { CapacitorConfig } from '@capacitor/cli'

// Set VITE_API_URL to your Railway URL before building for device
// e.g.  $env:VITE_API_URL = "https://your-app.up.railway.app"
const RAILWAY_URL = process.env.VITE_API_URL ?? 'https://your-app.up.railway.app'

const config: CapacitorConfig = {
  appId: 'com.cricketinsights.app',
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
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#0f172a',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER_CROP',
      showSpinner: false,
      splashFullScreen: true,
      splashImmersive: true,
      // iOS splash
      iosSpinnerStyle: 'small',
      spinnerColor: '#ff6b35',
    },
  },
}

export default config
