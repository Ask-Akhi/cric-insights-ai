# build-android.ps1 — Build and install Cricket Insights AI on Android
# Usage:
#   .\build-android.ps1              # build APK + auto-install via adb if phone connected
#   .\build-android.ps1 -OpenStudio  # open Android Studio (for emulator or manual run)
#
# Prerequisites: Android Studio + JDK 17 installed on this PC.

param([switch]$OpenStudio)

$ErrorActionPreference = 'Stop'
$root    = "c:\Users\1223505\Personal Apps"
$front   = "$root\frontend"
$android = "$front\android"
$apkSrc  = "$android\app\build\outputs\apk\debug\app-debug.apk"
$apkDest = "$root\CricketInsightsAI.apk"

Write-Host "`n🏏 Cricket Insights AI — Android Build" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

# ── 1. Build React (capacitor mode uses relative asset paths) ─────────────────
Write-Host "`n📦 [1/3] Building React app..." -ForegroundColor Yellow
Set-Location $front
npm run build:capacitor
if ($LASTEXITCODE -ne 0) { Write-Host "❌ React build failed" -ForegroundColor Red; exit 1 }

# ── 2. Sync into Android project ──────────────────────────────────────────────
Write-Host "`n🔄 [2/3] Syncing to Android project..." -ForegroundColor Yellow
npx cap sync android
if ($LASTEXITCODE -ne 0) { Write-Host "❌ cap sync failed" -ForegroundColor Red; exit 1 }

# ── 3a. Open Android Studio (emulator path) ───────────────────────────────────
if ($OpenStudio) {
    npx cap open android
    Write-Host "`n✅ Android Studio opened!" -ForegroundColor Green
    Write-Host "   → Wait for Gradle sync to finish"
    Write-Host "   → Select your phone or emulator in the device dropdown"
    Write-Host "   → Click the green ▶ Run button"
    exit 0
}

# ── 3b. Build APK via Gradle ──────────────────────────────────────────────────
Write-Host "`n🔨 [3/3] Building APK via Gradle..." -ForegroundColor Yellow
Set-Location $android
.\gradlew.bat assembleDebug --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Gradle build failed" -ForegroundColor Red; exit 1 }

Copy-Item $apkSrc $apkDest -Force
Write-Host "`n✅ APK built: $apkDest" -ForegroundColor Green

# ── Try adb auto-install if phone is plugged in ───────────────────────────────
$adbCmd = Get-Command adb -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $adbCmd) {
    foreach ($c in @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "$env:USERPROFILE\AppData\Local\Android\Sdk\platform-tools\adb.exe"
    )) { if (Test-Path $c) { $adbCmd = $c; break } }
}

if ($adbCmd) {
    $devices = & $adbCmd devices | Select-String "device$"
    if ($devices) {
        Write-Host "`n📱 Phone detected — installing via adb..." -ForegroundColor Yellow
        & $adbCmd install -r $apkSrc
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Installed! Open 'Cricket Insights AI' on your phone." -ForegroundColor Green
        } else {
            Write-Host "⚠  adb install failed — use manual install below." -ForegroundColor Yellow
        }
    } else {
        Write-Host "`n⚠  No phone detected via USB." -ForegroundColor Yellow
    }
} else {
    Write-Host "`n⚠  adb not found (Android Studio not installed)." -ForegroundColor Yellow
}

Write-Host "`n📤 Manual install options:" -ForegroundColor Cyan
Write-Host "   • USB:          copy  CricketInsightsAI.apk  to your phone, tap to install"
Write-Host "   • WhatsApp/Drive: share CricketInsightsAI.apk, open on phone → Install"
Write-Host "   • Phone must allow: Settings → Install unknown apps → [your file manager] → Allow`n"
