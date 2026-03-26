# 📱 iOS Build Guide — Cricket Insights AI on Mac + iPhone

> **Situation:** Xcode is installed on your MacBook. Your code lives on a Windows PC and GitHub.
> The Mac is a **fresh device** — you'll clone the repo here and build from it.
> Do every step **on the Mac** in Terminal order.

---

## ⚠️ OLD MAC / XCODE 14 SPECIFIC NOTES (Read First!)

Your Mac has **Xcode 14.0.1** — this is an older version but it **will work** for USB testing on your iPhone. A few things to know:

| Issue | What to do |
|---|---|
| Homebrew `formula.jws.json` error | Already fixed with `brew update-reset` ✅ |
| `ada-url` / `llvm` takes hours to compile | **Use nvm instead of Homebrew for Node** (see Step 2 below) |
| Xcode 14.0.1 can't build for iOS 17+ simulators | Use your physical iPhone via USB — works fine |
| CocoaPods may conflict with system Ruby | Use `sudo gem install cocoapods` then `pod --version` |
| `npx cap sync ios` may warn about Capacitor 8 + Xcode 14 | It still works — ignore the warning |

---

## ✅ Quick Checklist (copy to Notes app on Mac)

```
[ ] 1.  brew update-reset done ✅ (already completed)
[ ] 2.  Install Node via nvm (NOT brew install node)
[ ] 3.  sudo xcodebuild -license accept
[ ] 4.  xcode-select --install
[ ] 5.  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
[ ] 6.  xcodebuild -version  → shows Xcode 14.x
[ ] 7.  sudo gem install cocoapods  →  pod --version works
[ ] 8.  git clone https://github.com/Ask-Akhi/cric-insights-ai.git
[ ] 9.  cd cric-insights-ai/frontend && npm install
[ ] 10. Set Railway URL:  export VITE_API_URL=https://YOUR-APP.up.railway.app
[ ] 11. npm run cap:build:ios   (builds + syncs in one command)
[ ] 12. cd ios/App && pod install
[ ] 13. npx cap open ios  →  .xcworkspace opens in Xcode
[ ] 14. Apple ID added, Team set, Bundle ID set to unique value
[ ] 15. iPhone plugged in via USB + "Trust" tapped
[ ] 16. ▶ clicked in Xcode → App running on iPhone 🎉
```

---

## STEP 1 — Xcode Setup (already installed)

Since Homebrew update-reset is done, just accept the Xcode license:

```bash
sudo xcodebuild -license accept
xcode-select --install
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcodebuild -version
```
✅ Should print `Xcode 14.x`. That's fine for USB iPhone testing.

---

## STEP 2 — Install Node via nvm (SKIP brew install node)

> ⚠️ **Do NOT use `brew install node`** on your old Mac — it tries to compile `ada-url` via `llvm` which takes 2+ hours. Use `nvm` instead — it downloads a pre-built binary in 30 seconds.

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```

**Close Terminal and reopen it**, then:

```bash
nvm install 20
nvm use 20
node -v   # should print v20.x.x
npm -v    # should print 10.x.x
```

---

## STEP 3 — Install CocoaPods

```bash
sudo gem install cocoapods
pod --version
```
✅ Should print `1.x.x`.

If it fails with SSL error:
```bash
sudo gem update --system
sudo gem install cocoapods --source https://rubygems.org
```

---

## STEP 4 — Clone the Repo on Mac

```bash
cd ~
git clone https://github.com/Ask-Akhi/cric-insights-ai.git
cd cric-insights-ai/frontend
```

---

## STEP 5 — Install npm Packages

```bash
npm install
```
✅ Should end with no errors (some warnings are fine).

---

## STEP 6 — Set Your Railway URL (IMPORTANT)

The app on iPhone needs to call your live Railway backend. Set this before building:

```bash
export VITE_API_URL=https://YOUR-ACTUAL-APP.up.railway.app
```

> Replace `YOUR-ACTUAL-APP` with your real Railway app URL (find it in the Railway dashboard).
> To make it permanent, add that line to `~/.zshrc` and run `source ~/.zshrc`.

---

## STEP 7 — Build + Sync iOS (one command)

```bash
npm run cap:build:ios
```

This runs `vite build --mode capacitor` then `npx cap sync ios` automatically.

✅ Should end with:
```
✔  Copying web assets from dist to ios/App/App/public
✔  Updating iOS native dependencies
```

---

## STEP 8 — Install iOS Native Pods

```bash
cd ios/App
pod install
```
First run takes 1–3 min. You'll see:
```
Pod installation complete! There are X dependencies from the Podfile
```

Go back:
```bash
cd ../..
```

---

## STEP 9 — Open in Xcode

```bash
npx cap open ios
```

> ⚠️ Always use `.xcworkspace` NOT `.xcodeproj`. If Xcode opens the wrong one:
> ```bash
> open ~/cric-insights-ai/frontend/ios/App/App.xcworkspace
> ```

---

## STEP 10 — Sign with Apple ID (free, no $99 needed)

In Xcode:
1. Click the **App** project (blue icon, top of sidebar)
2. **TARGETS → App → Signing & Capabilities**
3. ✅ Check **Automatically manage signing**
4. **Team** → **Add an Account** → sign in with Apple ID
5. Change **Bundle Identifier** to something unique:
   ```
   com.akhi2026.cricinsightsai
   ```

---

## STEP 11 — Connect iPhone + Run

1. Plug iPhone into Mac via USB → tap **Trust** on iPhone
2. In Xcode top toolbar: click device selector → choose your iPhone
3. Click **▶ Play**

Xcode compiles (~60–120 seconds on Xcode 14) then installs on your iPhone.

> **"Untrusted Developer" on iPhone?**
> Settings → General → VPN & Device Management → [Your Apple ID] → **Trust**
> Then press ▶ in Xcode again.

🎉 **Cricket Insights AI is running on your iPhone!**

---

## 🔄 Updating After Code Changes (Windows → iPhone)

### On Windows PC:
```powershell
cd "c:\Users\1223505\Personal Apps\frontend"
git add -A
git commit -m "update: ..."
git push origin master
```

### On Mac (pull + rebuild + reinstall):
```bash
cd ~/cric-insights-ai
git pull origin master
cd frontend
export VITE_API_URL=https://YOUR-APP.up.railway.app
npm run cap:build:ios
npx cap open ios
```
Then click **▶** in Xcode.

---

## 🐞 Troubleshooting

| Problem | Fix |
|---|---|
| `node` not found after nvm install | Close & reopen Terminal, run `nvm use 20` |
| `xcodebuild -version` shows wrong path | `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` |
| `pod install` fails SSL error | `sudo gem update --system && sudo gem install cocoapods` |
| `pod install` hangs | `pod install --repo-update` |
| `npx cap sync ios` — "ios platform not found" | `npx cap add ios` then redo pod install |
| Xcode "No account" under Team | Xcode → Settings (⌘,) → Accounts → + → add Apple ID |
| "Untrusted Developer" on iPhone | Settings → General → VPN & Device Management → Trust |
| Bundle ID red error | Use more unique ID: `com.akhi2026.cricinsightsai2` |
| App loads but API calls fail | Check `VITE_API_URL` was set before `npm run cap:build:ios` |
| App crashes on launch | Xcode → View → Debug Area → Activate Console |
| iPhone not in device selector | Unplug → replug → wait for Trust prompt |
| Xcode 14 warning about Swift version | Ignore — doesn't block the build |

---

## 📋 Free vs Paid Apple Developer

| Feature | Free Apple ID | $99/yr |
|---|:---:|:---:|
| Run on your iPhone via USB | ✅ | ✅ |
| App expires every 7 days (re-run ▶) | ⚠️ | ❌ |
| TestFlight / share with others | ❌ | ✅ |
| App Store publish | ❌ | ✅ |

> **For personal testing, the free Apple ID is fine.**

```
[ ] 1.  Xcode opened & license accepted (GUI)
[ ] 2.  sudo xcodebuild -license accept
[ ] 3.  xcode-select --install
[ ] 4.  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
[ ] 5.  node -v  shows a version  (Node.js installed)
[ ] 6.  sudo gem install cocoapods
[ ] 7.  git clone https://github.com/Ask-Akhi/cric-insights-ai.git
[ ] 8.  cd frontend && npm install
[ ] 9.  npm run build
[ ] 10. npx cap sync ios
[ ] 11. cd ios/App && pod install
[ ] 12. cd ../.. && npx cap open ios  →  .xcworkspace opens in Xcode
[ ] 13. Apple ID added, Team set, Bundle ID changed to unique value
[ ] 14. iPhone plugged in via USB + "Trust" tapped on iPhone
[ ] 15. ▶ clicked in Xcode → App running on iPhone 🎉
```

---

## STEP 1 — First-time Xcode Setup

### 1a. Open Xcode and accept the license
- Open **Finder → Applications → Xcode**
- Click **Agree** on the license dialog
- Wait for it to finish installing additional components (2–5 min)

### 1b. Accept the license from Terminal too
Open **Terminal** (press ⌘ Space, type `Terminal`, press Enter) and run:
```bash
sudo xcodebuild -license accept
```
Enter your Mac password when prompted.

### 1c. Install Xcode Command Line Tools
```bash
xcode-select --install
```
A pop-up appears → click **Install** → wait ~2 min.
If it says "already installed" → that's fine, continue.

### 1d. Point command-line tools at Xcode (important!)
```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcodebuild -version
```
✅ Should print `Xcode 16.x` (or similar). If it does, you're good.

---

## STEP 2 — Install Node.js (if not already on Mac)

Check first:
```bash
node -v
npm -v
```
If both print version numbers → **skip to Step 3**.

Otherwise install via Homebrew:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install node
```
> After Homebrew installs, it may print two `eval` commands — copy/paste and run both of them, then reopen Terminal.

---

## STEP 3 — Install CocoaPods

CocoaPods manages iOS native dependencies that Capacitor needs.
```bash
sudo gem install cocoapods
```
Verify it worked:
```bash
pod --version
```
✅ Should print `1.x.x`.

If it hangs or fails, try:
```bash
sudo gem install cocoapods --source https://rubygems.org
```

---

## STEP 4 — Clone the Repo on Mac

```bash
cd ~
git clone https://github.com/Ask-Akhi/cric-insights-ai.git
cd cric-insights-ai/frontend
```

---

## STEP 5 — Install npm Packages & Build the Web App

```bash
npm install
npm run build
```
✅ Should end with `built in X.XXs` and no errors.

---

## STEP 6 — Sync Capacitor iOS

```bash
npx cap sync ios
```
This copies your built web app into the native iOS Xcode project.

✅ Should print:
```
✔  Copying web assets from dist to ios/App/App/public
✔  Updating iOS native dependencies
```

---

## STEP 7 — Install iOS Native Pods

```bash
cd ios/App
pod install
```
Downloads Capacitor's native iOS libraries. Takes 1–3 min on first run.

✅ Should end with:
```
Pod installation complete! There are X dependencies from the Podfile
```

Go back to the frontend folder:
```bash
cd ../..
```

---

## STEP 8 — Open in Xcode

```bash
npx cap open ios
```
This automatically opens `ios/App/App.xcworkspace` in Xcode.

> ⚠️ **Always open `.xcworkspace`, NOT `.xcodeproj`**
> If Xcode opens the wrong file, close it and manually run:
> ```bash
> open ~/cric-insights-ai/frontend/ios/App/App.xcworkspace
> ```

---

## STEP 9 — Sign the App with Your Apple ID

**You do NOT need to pay $99/yr — a free Apple ID works for USB iPhone testing.**

In Xcode:

1. Click the **App** project in the left sidebar (blue icon at the very top)
2. Under **TARGETS**, click **App**
3. Click the **Signing & Capabilities** tab
4. Check ✅ **Automatically manage signing**
5. Under **Team**, click the dropdown → **Add an Account...**
6. Sign in with your **Apple ID**
7. Select your name as the Team (e.g. `Your Name (Personal Team)`)
8. Change the **Bundle Identifier** to something unique — lowercase, no spaces:
   ```
   com.akhi2026.cricinsights
   ```
   > If you see a red "failed to create provisioning profile" error, make the bundle ID more unique, e.g. `com.akhi2026.cricinsightsai`

---

## STEP 10 — Connect Your iPhone via USB

1. Plug your iPhone into the Mac with a **USB cable**
2. On iPhone: tap **Trust** on the "Trust This Computer?" prompt → enter passcode
3. In Xcode, click the **device selector** in the top toolbar (next to the ▶ button — it shows a device name like "iPhone 15")
4. Your iPhone should appear in the list → click it to select it

> If your iPhone doesn't appear: unplug, replug, and wait 10 seconds.

---

## STEP 11 — Build & Run on iPhone ▶

Click the **▶ Play button** (top-left corner of Xcode).

Xcode will:
1. Compile the app (~30–90 seconds on first build)
2. Install it on your iPhone automatically
3. Launch the **Cricket Insights AI** app on your iPhone

> ⚠️ **If iPhone shows "Untrusted Developer" error:**
> On iPhone → **Settings → General → VPN & Device Management → [Your Apple ID] → Trust**
> Then press ▶ in Xcode again.

🎉 **The app is now running natively on your iPhone!**

---

## 🔄 Updating the App After Code Changes on Windows

### On Windows PC (after editing frontend code):
```powershell
cd "c:\Users\1223505\Personal Apps\frontend"
npm run build
npx cap sync ios
git add -A
git commit -m "update: sync capacitor ios"
git push origin master
```

### On Mac (pull latest → rebuild → reinstall on iPhone):
```bash
cd ~/cric-insights-ai
git pull origin master
cd frontend
npx cap sync ios
# Only needed if you added new Capacitor plugins:
# cd ios/App && pod install && cd ../..
npx cap open ios
```
Then click **▶** in Xcode — the updated app installs on iPhone.

---

## 🐞 Troubleshooting

| Problem | Fix |
|---------|-----|
| `xcodebuild -version` shows wrong path | `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` |
| `pod install` fails with SSL error | `sudo gem update --system && sudo gem install cocoapods` |
| `pod install` hangs at "Analyzing dependencies" | `pod install --repo-update` |
| `npx cap sync ios` — "ios platform not found" | `npx cap add ios` first, then redo pod install |
| Xcode shows "No account" under Team | Xcode → Settings (⌘,) → Accounts → + → add Apple ID |
| "Untrusted Developer" on iPhone | Settings → General → VPN & Device Management → Trust |
| Bundle ID red error "profile failed" | Change to a more unique ID e.g. `com.akhi2026.cricinsightsai2` |
| App crashes on launch | Xcode → View → Debug Area → Activate Console → read the error |
| iPhone not showing in device selector | Unplug → replug USB → check iPhone shows "Trust" prompt |
| `npx cap open ios` opens `.xcodeproj` | `open ios/App/App.xcworkspace` manually in Terminal |
| Node not found after Homebrew install | Run the two `eval` lines Homebrew printed, then reopen Terminal |
| `npm run build` fails on Mac | Make sure you ran `npm install` first |

---

## 📋 Free vs Paid Apple Developer

| Feature | Free Apple ID | $99/yr Developer Account |
|---------|:---:|:---:|
| Run on your own iPhone via USB | ✅ | ✅ |
| App expires every 7 days (re-run ▶ to refresh) | ⚠️ | ❌ no expiry |
| Max 3 devices at once | ✅ | ✅ unlimited |
| TestFlight (share with others) | ❌ | ✅ |
| App Store publish | ❌ | ✅ |

> **For personal testing on your own iPhone, the free Apple ID is perfectly fine.**
