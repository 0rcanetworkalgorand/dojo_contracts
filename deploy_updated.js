const algosdk = require('algosdk');
const fs = require('fs');
const dotenv = require('dotenv');

dotenv.config();

async function main() {
    console.log('============================================================');
    console.log('🥋 0rca Swarm Dojo - Deploy Updated Contracts (TestNet)');
    console.log('============================================================\n');

    const mnemonic = process.env.ADMIN_MNEMONIC || process.env.ADMIN_PASSPHRASE;
    if (!mnemonic) throw new Error('No mnemonic found in .env');

    const account = algosdk.mnemonicToSecretKey(mnemonic);
    console.log(`🔑 Admin: ${account.addr}\n`);

    const algodClient = new algosdk.Algodv2(
        process.env.ALGOD_TOKEN || '',
        process.env.ALGOD_SERVER || 'https://testnet-api.algonode.cloud',
        parseInt(process.env.ALGOD_PORT || '443')
    );

    const accountInfo = await algodClient.accountInformation(account.addr).do();
    console.log(`💰 Balance: ${(Number(accountInfo.amount) / 1_000_000).toFixed(6)} ALGO\n`);

    const contracts = [
        {
            name: 'EscrowVault',
            approvalPath: 'projects/smart_contracts/escrow_vault/artifacts/EscrowVault.approval.teal',
            clearPath: 'projects/smart_contracts/escrow_vault/artifacts/EscrowVault.clear.teal',
            arc56Path: 'projects/smart_contracts/escrow_vault/artifacts/EscrowVault.arc56.json',
            globalInts: 2,
            globalBytes: 1,
            createArgs: [{ type: 'address', value: account.addr }],
        },
        {
            name: 'CommitmentLock',
            approvalPath: 'projects/smart_contracts/commitment_lock/artifacts/CommitmentLock.approval.teal',
            clearPath: 'projects/smart_contracts/commitment_lock/artifacts/CommitmentLock.clear.teal',
            arc56Path: 'projects/smart_contracts/commitment_lock/artifacts/CommitmentLock.arc56.json',
            globalInts: 2,
            globalBytes: 2,
            createArgs: [
                { type: 'address', value: account.addr },
                { type: 'address', value: account.addr },
            ],
        },
    ];

    const results = {};

    for (const contract of contracts) {
        console.log('------------------------------------------------------------');
        console.log(`📦 Deploying: ${contract.name}`);
        console.log('------------------------------------------------------------');

        try {
            const approvalProgram = fs.readFileSync(contract.approvalPath, 'utf8');
            const clearProgram = fs.readFileSync(contract.clearPath, 'utf8');

            console.log('🔨 Compiling TEAL on-chain...');
            const approvalCompiled = await algodClient.compile(approvalProgram).do();
            const clearCompiled = await algodClient.compile(clearProgram).do();

            const approvalBytes = new Uint8Array(Buffer.from(approvalCompiled.result, 'base64'));
            const clearBytes = new Uint8Array(Buffer.from(clearCompiled.result, 'base64'));
            console.log(`   Approval: ${approvalBytes.length} bytes, Clear: ${clearBytes.length} bytes`);

            // Check if we need extra pages (each page is 2048 bytes)
            const extraPages = Math.max(0, Math.ceil(approvalBytes.length / 2048) - 1);
            if (extraPages > 0) {
                console.log(`   ⚠️ Program needs ${extraPages} extra page(s)`);
            }

            const arc56 = JSON.parse(fs.readFileSync(contract.arc56Path, 'utf8'));
            const createMethod = arc56.methods.find(m => m.name === 'create');
            if (!createMethod) throw new Error('create method not found in ARC56');

            const abiMethod = new algosdk.ABIMethod(createMethod);
            const appArgs = [abiMethod.getSelector()];

            for (let i = 0; i < contract.createArgs.length; i++) {
                const arg = contract.createArgs[i];
                if (createMethod.args[i].type === 'address') {
                    appArgs.push(algosdk.decodeAddress(String(arg.value)).publicKey);
                } else if (createMethod.args[i].type === 'uint64') {
                    const encoded = new Uint8Array(8);
                    new DataView(encoded.buffer).setBigUint64(0, BigInt(arg.value), false);
                    appArgs.push(encoded);
                }
            }

            const params = await algodClient.getTransactionParams().do();

            const txn = algosdk.makeApplicationCreateTxnFromObject({
                sender: account.addr,
                suggestedParams: params,
                onComplete: algosdk.OnApplicationComplete.NoOpOC,
                approvalProgram: approvalBytes,
                clearProgram: clearBytes,
                numGlobalInts: contract.globalInts,
                numGlobalByteSlices: contract.globalBytes,
                numLocalInts: 0,
                numLocalByteSlices: 0,
                appArgs,
                extraPages,
            });

            console.log('✍️  Signing...');
            const signedTxn = txn.signTxn(account.sk);

            console.log('📤 Sending to TestNet...');
            const txResponse = await algodClient.sendRawTransaction(signedTxn).do();
            const txId = txResponse.txid;
            console.log(`   TxID: ${txId}`);

            console.log('⏳ Waiting for confirmation...');
            const confirmed = await algosdk.waitForConfirmation(algodClient, txId, 4);
            const appId = Number(confirmed.applicationIndex || 0);

            results[contract.name] = appId;

            console.log(`✅ ${contract.name} deployed!`);
            console.log(`   App ID: ${appId}`);
            console.log(`   App Address: ${algosdk.getApplicationAddress(appId)}`);
            console.log(`   Explorer: https://testnet.explorer.perawallet.app/application/${appId}\n`);

        } catch (error) {
            console.error(`❌ Failed to deploy ${contract.name}: ${error.message}`);
            throw error;
        }
    }

    console.log('============================================================');
    console.log('📊 DEPLOYMENT RESULTS');
    console.log('============================================================');
    for (const [name, appId] of Object.entries(results)) {
        console.log(`   ${name}: ${appId}`);
    }
    console.log('============================================================\n');

    // Save results
    const outputData = { network: 'testnet', timestamp: new Date().toISOString(), contracts: results };
    fs.writeFileSync('deployment_updated.json', JSON.stringify(outputData, null, 2));
    console.log('💾 Saved to deployment_updated.json');
}

main().catch(err => { console.error('Deploy failed:', err.message); process.exit(1); });
