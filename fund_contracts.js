const algosdk = require('algosdk');
const dotenv = require('dotenv');
dotenv.config();

async function fund() {
    const mnemonic = process.env.ADMIN_MNEMONIC || process.env.ADMIN_PASSPHRASE;
    const account = algosdk.mnemonicToSecretKey(mnemonic);
    const algodClient = new algosdk.Algodv2('', 'https://testnet-api.algonode.cloud', 443);

    const contracts = [
        { name: 'EscrowVault', appId: 761941677 },
        { name: 'CommitmentLock', appId: 761941684 },
    ];

    for (const c of contracts) {
        const appAddr = algosdk.getApplicationAddress(c.appId);
        
        // Check current balance
        const info = await algodClient.accountInformation(appAddr).do();
        const bal = Number(info.amount) / 1_000_000;
        console.log(`${c.name} (${appAddr}): ${bal.toFixed(6)} ALGO`);
        
        if (bal < 0.5) {
            console.log(`  → Funding with 1 ALGO...`);
            const sp = await algodClient.getTransactionParams().do();
            const txn = algosdk.makePaymentTxnWithSuggestedParamsFromObject({
                sender: account.addr,
                receiver: appAddr,
                amount: 1_000_000, // 1 ALGO
                suggestedParams: sp,
            });
            const signed = txn.signTxn(account.sk);
            const { txid } = await algodClient.sendRawTransaction(signed).do();
            await algosdk.waitForConfirmation(algodClient, txid, 4);
            console.log(`  ✅ Funded! TxId: ${txid}`);
        } else {
            console.log(`  → Already funded (${bal.toFixed(6)} ALGO)`);
        }
    }
}

fund().catch(e => console.error(e));
