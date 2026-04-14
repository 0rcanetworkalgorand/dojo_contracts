const algosdk = require('algosdk');

async function main() {
    const mnemonic = "bracket inform cricket pact impact mask misery quantum dismiss giant fog mechanic category royal east actual gold easily snow laundry vast gown crater absent denial";
    const account = algosdk.mnemonicToSecretKey(mnemonic);
    const address = account.addr.toString();
    console.log("Account:", address);

    const algod = new algosdk.Algodv2('', 'https://testnet-api.algonode.cloud', '');
    const indexer = new algosdk.Indexer('', 'https://testnet-idx.algonode.cloud', '');

    const accountInfo = await indexer.lookupAccountCreatedApplications(address).do();
    const apps = accountInfo.applications || [];
    console.log(`Found ${apps.length} apps created by this account.`);

    let deleted = 0;
    for (const app of apps) {
        if (deleted >= 3) break; 
        console.log(`Deleting app ${app.id}...`);
        try {
            const sp = await algod.getTransactionParams().do();
            const txn = algosdk.makeApplicationDeleteTxn(address, sp, app.id);
            const signed = txn.signTxn(account.sk);
            const { txId } = await algod.sendRawTransaction(signed).do();
            console.log(`Sent delete tx for app ${app.id}: ${txId}`);
            await algosdk.waitForConfirmation(algod, txId, 4);
            console.log(`Deleted app ${app.id}`);
            deleted++;
        } catch (e) {
            console.error(`Failed to delete app ${app.id}: ${e.message}`);
        }
    }
}

main().catch(console.error);
