#!/usr/bin/env node
/** Generate checksums.txt for release artifacts */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const releaseDir = path.join(__dirname, '..', 'release');
const files = fs.readdirSync(releaseDir).filter(f => f.endsWith('.exe') || f.endsWith('.blockmap'));

let output = '# MAIOS Release Checksums\n';
output += `# Generated: ${new Date().toISOString()}\n\n`;

for (const file of files) {
  const buf = fs.readFileSync(path.join(releaseDir, file));
  const hash = crypto.createHash('sha256').update(buf).digest('hex');
  output += `${hash}  ${file}\n`;
}

fs.writeFileSync(path.join(releaseDir, 'checksums.txt'), output);
console.log('checksums.txt written to release/');
