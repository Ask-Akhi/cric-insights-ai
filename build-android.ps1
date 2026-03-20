# build-android.ps1 — Builds Cricket Insights AI APK for Android
# Usage: .\build-android.ps1
# Prerequisites: Android Studio + JDK 17 installed, `npx cap add android` run once.

$ErrorActionPreference = 'Stop'
$root    = "c:\Users\1223505\Personal Apps"
$front   = "$root\frontend"
$android = "$front\android"
$apkSrc  = "$android\app\build\outputs\apk\debug\app-debug.apk"
$apkDest = "$root\CricketInsightsAI.apk"

Write-Host "`n🏏 Cricket Insights AI — Android APK Builder" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

# 1. Build React with Capacitor mode (relative asset paths)
Write-Host "`n📦 [1/3] Building React app (capacitor mode)..." -ForegroundColor Yellow
Set-Location $front
npm run build:capacitor
if ($LASTEXITCODE -ne 0) { Write-Host "❌ React build failed" -ForegroundColor Red; exit 1 }

# 2. Sync built files into the Android project
Write-Host "`n🔄 [2/3] Syncing to Android project..." -ForegroundColor Yellow
npx cap sync android
if ($LASTEXITCODE -ne 0) { Write-Host "❌ cap sync failed" -ForegroundColor Red; exit 1 }

# 3. Build APK via Gradle (debug — no signing needed)
Write-Host "`n🔨 [3/3] Building APK via Gradle..." -ForegroundColor Yellow
Set-Location $android
.\gradlew.bat assembleDebug --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Gradle build failed" -ForegroundColor Red; exit 1 }

# 4. Copy APK to root folder for easy sharing
Copy-Item $apkSrc $apkDest -Force

Write-Host "`n✅  APK ready!" -ForegroundColor Green
Write-Host "📱  Location : $apkDest" -ForegroundColor Green
Write-Host "📤  Share via WhatsApp / Telegram / Google Drive" -ForegroundColor Green
Write-Host "     Receivers: tap file → Install → allow 'Unknown sources' once`n" -ForegroundColor DarkGray
