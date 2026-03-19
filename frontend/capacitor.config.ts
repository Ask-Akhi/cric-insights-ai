import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.cricketinsights.app',
  appName: 'Cricket Insights AI',
  webDir: 'dist',
  server: {
    // Always use HTTPS on device; cleartext HTTP is blocked by Android by default
    androidScheme: 'https',
    cleartext: false,
  },
  android: {
    backgroundColor: '#0f172a',
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
    },
  },
}

export default config
