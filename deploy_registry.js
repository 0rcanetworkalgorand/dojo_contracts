const algosdk = require('algosdk');
const fs = require('fs');
const path = require('path');

async function main() {
    // Load .env manually
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

    // Connect to Algod
    const client = new algosdk.Algodv2(
        envVars.ALGOD_TOKEN || '',
        envVars.ALGOD_SERVER || 'https://testnet-api.algonode.cloud',
        envVars.ALGOD_PORT || '443'
    );

    // Check balance
    const accountInfo = await client.accountInformation(adminAddr).do();
    console.log('Balance:', Number(accountInfo.amount) / 1e6, 'ALGO');

    // Get suggested params
    const params = await client.getTransactionParams().do();
    params.fee = BigInt(3000);
    params.flatFee = true;

    // Create app transaction with admin address as arg
    const appArgs = [Buffer.from(adminAddr, 'utf8')];

    // Create app transaction
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

    console.log('Signing transaction...');
    const signedTxn = txn.signTxn(account.sk);
    
    console.log('Sending transaction...');
    const sendResult = await client.sendRawTransaction(signedTxn).do();
    console.log('TxID:', sendResult.txid);

    console.log('Waiting for confirmation...');
    const confirmed = await algosdk.waitForConfirmation(client, sendResult.txid, 4);
    console.log('App ID:', confirmed.applicationIndex);
    
    console.log('\n=== DEPLOYMENT SUCCESSFUL ===');
    console.log('DojoRegistry App ID:', confirmed.applicationIndex);
    console.log('Update your .env with: DOJO_REGISTRY_APP_ID=' + confirmed.applicationIndex);
}

main().catch(console.error);
