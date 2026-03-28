#!/usr/bin/env node
/**
 * scripts/patch-spm.cjs
 *
 * Ensures Xcode 14 (max Swift tools 5.7) can resolve all @capacitor SPM packages.
 *
 * Strategy: copy the vendored ios/vendor/splash-screen-Package.swift (5.7, iOS 13)
 * directly over node_modules/@capacitor/splash-screen/Package.swift, which ships
 * as 5.9 from npm and cannot be changed via npm.
 *
 * Also does a regex fallback patch on any other @capacitor Package.swift files
 * that still declare swift-tools-version: 5.9.
 *
 * Runs automatically via:
 *   - "postinstall" npm script  (after npm install)
 *   - "cap:sync:ios" npm script (after npx cap sync ios)
 *   - "cap:open:ios" npm script (before open App.xcworkspace)
 *
 * Safe to run multiple times (idempotent).
 * NO-OP on non-macOS (Docker/Linux/Windows).
 */
'use strict';

if (process.platform !== 'darwin') {
  console.log('[patch-spm] Non-macOS (' + process.platform + ') -- skipping.');
  process.exit(0);
}

var fs = require('fs');
var path = require('path');

var frontendDir = path.join(__dirname, '..');
var vendorFile  = path.join(frontendDir, 'ios', 'vendor', 'splash-screen-Package.swift');
var targetFile  = path.join(frontendDir, 'node_modules', '@capacitor', 'splash-screen', 'Package.swift');

// -- Step 1: copy vendored Package.swift over the npm one --------------------
if (!fs.existsSync(vendorFile)) {
  console.error('[patch-spm] ERROR: vendored file missing: ' + vendorFile);
  console.error('[patch-spm] Run: git pull origin master');
  process.exit(1);
}

if (!fs.existsSync(targetFile)) {
  console.log('[patch-spm] node_modules/@capacitor/splash-screen not installed yet -- skipping copy.');
} else {
  var vendored = fs.readFileSync(vendorFile, 'utf8');
  var current  = fs.readFileSync(targetFile, 'utf8');
  if (current === vendored) {
    console.log('[patch-spm] splash-screen/Package.swift already matches vendor -- OK.');
  } else {
    fs.writeFileSync(targetFile, vendored, 'utf8');
    console.log('[patch-spm] Copied vendored Package.swift (5.7/iOS13) -> ' + targetFile);
  }
}

// -- Step 2: regex fallback -- patch any other @capacitor Package.swift 5.9 -
function findPackageSwift(dir, results) {
  results = results || [];
  if (!fs.existsSync(dir)) return results;
  var entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return results; }
  for (var i = 0; i < entries.length; i++) {
    var entry = entries[i];
    var full = path.join(dir, entry.name);
    if (entry.isDirectory()) { findPackageSwift(full, results); }
    else if (entry.name === 'Package.swift') { results.push(full); }
  }
  return results;
}

var capacitorDir = path.join(frontendDir, 'node_modules', '@capacitor');
var allSwift = findPackageSwift(capacitorDir);
var patched = 0, alreadyOk = 0;

for (var j = 0; j < allSwift.length; j++) {
  var f = allSwift[j];
  var src = fs.readFileSync(f, 'utf8');
  if (src.indexOf('swift-tools-version: 5.9') === -1) { alreadyOk++; continue; }
  fs.writeFileSync(f, src.replace(/swift-tools-version:\s*5\.9/g, 'swift-tools-version: 5.7'), 'utf8');
  console.log('[patch-spm] Regex-patched 5.9->5.7: ' + f);
  patched++;
}

console.log('[patch-spm] Done -- ' + patched + ' regex-patched, ' + alreadyOk + ' already OK.');