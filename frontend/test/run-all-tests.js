const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const testDir = __dirname;
const testFiles = fs.readdirSync(testDir).filter(f => f.endsWith('.test.ts'));
const sucraseNodeScript = path.resolve(__dirname, '../node_modules/sucrase/bin/sucrase-node');

console.log(`Discovered ${testFiles.length} test files in ${testDir}`);

let totalPassed = 0;
let totalFailed = 0;

for (const file of testFiles) {
  const filePath = path.join(testDir, file);
  console.log(`\n========================================`);
  console.log(`RUNNING: ${file}`);
  console.log(`========================================`);
  const res = spawnSync(process.execPath, [sucraseNodeScript, filePath], { stdio: 'inherit' });
  if (res.status !== 0) {
    console.error(`FAILED: ${file} (Exit code: ${res.status})`);
    totalFailed++;
    process.exit(res.status || 1);
  } else {
    totalPassed++;
  }
}

console.log(`\n========================================`);
console.log(`ALL TEST SUITES PASSED (${totalPassed} suites)`);
console.log(`========================================\n`);
