#!/usr/bin/env node
/**
 * scripts/patch-spm.cjs
 *
 * Patches @capacitor/splash-screen/Package.swift from swift-tools-version: 5.9
 * to 5.7 so Xcode 14 can resolve the SPM package.
 *
 * Runs automatically via the "postinstall" npm script after every npm install.
 * Safe to run multiple times (idempotent).
 */
'use strict';
const fs = require('fs');
const path = require('path');

const targets = [
  path.join(__dirname, '..', 'node_modules', '@capacitor', 'splash-screen', 'Package.swift'),
];

let patched = 0;

for (const filePath of targets) {
  if (!fs.existsSync(filePath)) {
    console.log(`[patch-spm] Not found (skip): ${filePath}`);
    continue;
  }

  const original = fs.readFileSync(filePath, 'utf8');

  if (!original.includes('swift-tools-version: 5.9')) {
    console.log(`[patch-spm] Already OK: ${filePath}`);
    continue;
  }

  const patched_content = original.replace(
    /swift-tools-version:\s*5\.9/g,
    'swift-tools-version: 5.7'
  );

  fs.writeFileSync(filePath, patched_content, 'utf8');
  console.log(`[patch-spm] Patched 5.9 -> 5.7: ${filePath}`);
  patched++;
}

console.log(`[patch-spm] Done — ${patched} file(s) patched.`);
