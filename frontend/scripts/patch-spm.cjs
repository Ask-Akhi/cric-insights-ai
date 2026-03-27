#!/usr/bin/env node
/**
 * scripts/patch-spm.cjs
 *
 * Patches ALL Package.swift files under node_modules/@capacitor/ from
 * swift-tools-version: 5.9 -> 5.7 so Xcode 14 (max Swift tools 5.7) can
 * resolve every SPM package in the CapApp-SPM dependency graph.
 *
 * Runs automatically via:
 *   - "postinstall" npm script  (after npm install)
 *   - "cap:sync:ios" npm script (after npx cap sync ios regenerates Package.swift)
 *
 * Safe to run multiple times (idempotent).
 *
 * NO-OP on non-macOS environments (Docker/Linux/Windows) -- Package.swift files
 * are only consumed by Xcode on macOS.
 */
'use strict';

// Only needed on macOS -- skip silently everywhere else (Docker, CI, Windows)
if (process.platform !== 'darwin') {
  console.log('[patch-spm] Non-macOS platform (' + process.platform + ') -- skipping SPM patch.');
  process.exit(0);
}

const fs = require('fs');
const path = require('path');

// Recursively find all Package.swift files under a directory
function findPackageSwift(dir, results) {
  results = results || [];
  if (!fs.existsSync(dir)) return results;
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch (_) { return results; }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      findPackageSwift(full, results);
    } else if (entry.name === 'Package.swift') {
      results.push(full);
    }
  }
  return results;
}

const capacitorModulesDir = path.join(__dirname, '..', 'node_modules', '@capacitor');
const allPackageSwift = findPackageSwift(capacitorModulesDir);

if (allPackageSwift.length === 0) {
  console.log('[patch-spm] No Package.swift files found under node_modules/@capacitor/ -- skipping.');
  process.exit(0);
}

let patched = 0;
let alreadyOk = 0;

for (const filePath of allPackageSwift) {
  const original = fs.readFileSync(filePath, 'utf8');
  if (!original.includes('swift-tools-version: 5.9')) {
    alreadyOk++;
    continue;
  }
  const fixed = original.replace(/swift-tools-version:\s*5\.9/g, 'swift-tools-version: 5.7');
  fs.writeFileSync(filePath, fixed, 'utf8');
  console.log('[patch-spm] Patched 5.9 -> 5.7: ' + filePath);
  patched++;
}

console.log('[patch-spm] Done -- ' + patched + ' patched, ' + alreadyOk + ' already OK.');