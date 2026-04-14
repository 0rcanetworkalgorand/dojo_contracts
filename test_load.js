const algosdk = require('algosdk');
const fs = require('fs');
const path = require('path');

// Load .env manually
const envPath = path.join(__dirname, '.env');
const envContent = fs.readFileSync(envPath, 'utf8');
const envVars = {};
envContent.split('\n').forEach(line => {
    const [key, ...valueParts] = line.split('=');
    if (key && valueParts.length > 0) envVars[key.trim()] = valueParts.join('=').trim();
});

const mnemonic = envVars.ADMIN_PASSPHRASE || envVars.ADMIN_MNEMONIC;
console.log('Mnemonic loaded:', mnemonic ? 'YES' : 'NO');

const account = algosdk.mnemonicToSecretKey(mnemonic);
console.log('Admin:', account.addr);

const approval = fs.readFileSync('projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal');
const clear = fs.readFileSync('projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal');

console.log('Approval size:', approval.length);
console.log('Clear size:', clear.length);
