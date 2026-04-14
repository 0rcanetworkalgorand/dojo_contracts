const algosdk = require('algosdk');
const fs = require('fs');
const path = require('path');

async function main() {
    const envPath = path.join(__dirname, '.env');
    const envContent = fs.readFileSync(envPath, 'utf8');
    const envVars = {};
    envContent.split('\n').forEach(line => {
        const [key, ...valueParts] = line.split('=');
        if (key && valueParts.length > 0) envVars[key.trim()] = valueParts.join('=').trim();
    });

    const mnemonic = envVars.ADMIN_PASSPHRASE || envVars.ADMIN_MNEMONIC;
    const account = algosdk.mnemonicToSecretKey(mnemonic);
    const adminAddr = account.addr.toString();
    console.log('Admin:', adminAddr);

    // Load contracts
    const approval = fs.readFileSync('projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal');
    const clear = fs.readFileSync('projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal');
    console.log('Approval size:', approval.length);

    const client = new algosdk.Algodv2(
        envVars.ALGOD_TOKEN || '',
        envVars.ALGOD_SERVER || 'https://testnet-api.algonode.cloud',
        envVars.ALGOD_PORT || '443'
    );

    const params = await client.getTransactionParams().do();
    const appArgs = [Buffer.from(adminAddr, 'utf8')];

    const txn = algosdk.makeApplicationCreateTxnFromObject({
        sender: adminAddr,
        suggestedParams: params,
        onComplete: algosdk.OnApplicationComplete.NoOpOC,
        approvalProgram: approval,
        clearProgram: clear,
        numGlobalInts: 1,
        numGlobalByteSlices: 1,
        numLocalInts: 0,
        numLocalByteSlices: 0,
        appArgs: appArgs,
    });

    console.log('Signing...');
    const signedTxn = txn.signTxn(account.sk);
    
    console.log('Sending...');
    const sendResult = await client.sendRawTransaction(signedTxn).do();
    console.log('TxID:', sendResult.txid);

    const confirmed = await algosdk.waitForConfirmation(client, sendResult.txid, 4);
    console.log('App ID:', confirmed.applicationIndex);
    
    console.log('\n=== NEW DojoRegistry deployed ===');
    console.log('App ID:', confirmed.applicationIndex);
    console.log('\nYou need to update:');
    console.log('1. dojo-backend/.env: DOJO_REGISTRY_APP_ID=' + confirmed.applicationIndex);
    console.log('2. dojo-frontend/.env.local: NEXT_PUBLIC_DOJO_REGISTRY_APP_ID=' + confirmed.applicationIndex);
}

main().catch(console.error);
