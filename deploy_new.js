const algosdk = require('algosdk');
const fs = require('fs');

async function main() {
    const mnemonic = "bracket inform cricket pact impact mask misery quantum dismiss giant fog mechanic category royal east actual gold easily snow laundry vast gown crater absent denial";
    const account = algosdk.mnemonicToSecretKey(mnemonic);
    const adminAddr = account.addr.toString();
    console.log('Admin:', adminAddr);

    const approval = fs.readFileSync('projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal');
    const clear = fs.readFileSync('projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal');
    console.log('Approval size:', approval.length, 'bytes');

    const client = new algosdk.Algodv2('', 'https://testnet-api.algonode.cloud', '443');
    const accountInfo = await client.accountInformation(adminAddr).do();
    console.log('Balance:', Number(accountInfo.amount) / 1e6, 'ALGO');

    const params = await client.getTransactionParams().do();
    params.fee = 70000;
    params.flatFee = true;
    params.lastValid = Number(params.firstValid) + 2000;

    // Try BARE app create (no app args) - then call create method separately
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
        extraPages: 4,
        appArgs: [],  // No args - bare app create
    });

    console.log('Signing transaction...');
    const signedTxn = txn.signTxn(account.sk);
    
    console.log('Sending transaction...');
    const sendResult = await client.sendRawTransaction(signedTxn).do();
    console.log('TxID:', sendResult.txid);

    console.log('Waiting for confirmation...');
    const confirmed = await algosdk.waitForConfirmation(client, sendResult.txid, 15);
    console.log('App ID:', confirmed.applicationIndex);
    
    // Now call create() method to set admin
    console.log('\nCalling create() to set admin...');
    const appId = confirmed.applicationIndex;
    
    const callParams = await client.getTransactionParams().do();
    callParams.fee = 2000;
    callParams.flatFee = true;
    
    const callTxn = algosdk.makeApplicationCallTxnFromObject({
        sender: adminAddr,
        suggestedParams: callParams,
        appId: appId,
        onComplete: algosdk.OnApplicationComplete.NoOpOC,
        appArgs: [Buffer.from('create'), Buffer.from(adminAddr, 'utf8')],
    });
    
    const signedCall = callTxn.signTxn(account.sk);
    const callResult = await client.sendRawTransaction(signedCall).do();
    console.log('Call TxID:', callResult.txid);
    
    await algosdk.waitForConfirmation(client, callResult.txid, 10);
    
    console.log('\n=== DEPLOYMENT SUCCESSFUL ===');
    console.log('DojoRegistry App ID:', appId);
    console.log('\nUpdate .env: DOJO_REGISTRY_APP_ID=' + appId);
}

main().catch(console.error);