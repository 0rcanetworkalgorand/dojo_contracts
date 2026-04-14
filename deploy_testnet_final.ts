import algosdk from 'algosdk';
import * as fs from 'fs';
import * as path from 'path';
import * as dotenv from 'dotenv';

// Load environment variables
dotenv.config();

interface DeploymentResult {
  network: string;
  deployer: {
    publicKey: Uint8Array;
  };
  timestamp: string;
  contracts: {
    [key: string]: number;
  };
}

interface ContractArg {
  type: string;
  value: any;
}

interface ContractConfig {
  name: string;
  description: string;
  approvalPath: string;
  clearPath: string;
  globalInts: number;
  globalBytes: number;
  localInts: number;
  localBytes: number;
  createArgs?: ContractArg[];
}

async function main() {
  console.log('============================================================');
  console.log('🥋 0rca Swarm Dojo - TestNet Deployment');
  console.log('============================================================\n');

  // Load mnemonic from .env (supports both ADMIN_MNEMONIC and ADMIN_PASSPHRASE)
  const mnemonic = process.env.ADMIN_MNEMONIC || process.env.ADMIN_PASSPHRASE;
  if (!mnemonic) {
    throw new Error('ADMIN_MNEMONIC or ADMIN_PASSPHRASE not found in .env file');
  }

  // Recover account from mnemonic
  console.log('🔑 Loading admin account from mnemonic...');
  const account = algosdk.mnemonicToSecretKey(mnemonic);
  console.log(`   Address: ${account.addr}\n`);

  // Connect to TestNet
  const algodServer = process.env.ALGOD_SERVER || 'https://testnet-api.algonode.cloud';
  const algodPort = parseInt(process.env.ALGOD_PORT || '443');
  const algodToken = process.env.ALGOD_TOKEN || '';

  console.log('📡 Connecting to Algorand TestNet...');
  console.log(`   Server: ${algodServer}`);
  
  const algodClient = new algosdk.Algodv2(algodToken, algodServer, algodPort);

  // Check connection and balance
  try {
    const accountInfo = await algodClient.accountInformation(account.addr).do();
    const balance = Number(accountInfo.amount) / 1_000_000;
    console.log(`   Balance: ${balance.toFixed(6)} ALGO\n`);

    if (balance < 0.5) {
      console.log('⚠️  Warning: Low balance. You may need more ALGO for deployment.');
      console.log('   Get TestNet ALGO: https://bank.testnet.algorand.network/\n');
    }
  } catch (error) {
    console.error('❌ Failed to connect to TestNet or fetch account info');
    throw error;
  }

  // Contract configurations
  const contracts: ContractConfig[] = [
    {
      name: 'DojoRegistry',
      description: 'Agent identity store with Box Storage',
      approvalPath: 'projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal',
      clearPath: 'projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal',
      globalInts: 1,
      globalBytes: 1,
      localInts: 0,
      localBytes: 0,
      createArgs: [{ type: 'address', value: account.addr }],
    },
    {
      name: 'EscrowVault',
      description: 'Per-task escrow with ALGO support',
      approvalPath: 'projects/smart_contracts/escrow_vault/artifacts/EscrowVault.approval.teal',
      clearPath: 'projects/smart_contracts/escrow_vault/artifacts/EscrowVault.clear.teal',
      globalInts: 2,
      globalBytes: 1,
      localInts: 0,
      localBytes: 0,
      createArgs: [
        { type: 'address', value: account.addr },
      ],
    },
    {
      name: 'CommitmentLock',
      description: 'Time-locked reputation stakes',
      approvalPath: 'projects/smart_contracts/commitment_lock/artifacts/CommitmentLock.approval.teal',
      clearPath: 'projects/smart_contracts/commitment_lock/artifacts/CommitmentLock.clear.teal',
      globalInts: 2,
      globalBytes: 2,
      localInts: 0,
      localBytes: 0,
      createArgs: [
        { type: 'address', value: account.addr },
        { type: 'address', value: account.addr },
      ], // admin, treasury
    },
    {
      name: 'PayoutSplitter',
      description: 'Multi-recipient ALGO distribution',
      approvalPath: 'projects/smart_contracts/payout_splitter/artifacts/PayoutSplitter.approval.teal',
      clearPath: 'projects/smart_contracts/payout_splitter/artifacts/PayoutSplitter.clear.teal',
      globalInts: 2,
      globalBytes: 1,
      localInts: 0,
      localBytes: 0,
      createArgs: [
        { type: 'address', value: account.addr },
      ],
    },
  ];

  const deploymentResult: DeploymentResult = {
    network: 'testnet',
    deployer: {
      publicKey: account.sk.slice(32), // Public key is last 32 bytes
    },
    timestamp: new Date().toISOString(),
    contracts: {},
  };

  // Deploy each contract
  for (const contract of contracts) {
    console.log('============================================================');
    console.log(`📦 Deploying: ${contract.name}`);
    console.log(`   Description: ${contract.description}`);
    console.log('============================================================');

    try {
      // Read TEAL files
      console.log('📄 Reading TEAL files...');
      const approvalProgram = fs.readFileSync(contract.approvalPath, 'utf8');
      const clearProgram = fs.readFileSync(contract.clearPath, 'utf8');

      // Compile programs
      console.log('🔨 Compiling programs...');
      const approvalCompiled = await algodClient.compile(approvalProgram).do();
      const clearCompiled = await algodClient.compile(clearProgram).do();

      // Get suggested params
      const params = await algodClient.getTransactionParams().do();

      // Read ARC56 file for ABI method info
      const arc56Path = contract.approvalPath.replace('.approval.teal', '.arc56.json');
      const arc56 = JSON.parse(fs.readFileSync(arc56Path, 'utf8'));
      const createMethod = arc56.methods.find((m: any) => m.name === 'create');
      
      if (!createMethod) {
        throw new Error(`Create method not found in ARC56 for ${contract.name}`);
      }

      // Encode create arguments using ABI
      console.log('📝 Encoding ABI arguments...');
      const abiMethod = new algosdk.ABIMethod(createMethod);
      const appArgs: Uint8Array[] = [];
      
      // Add method selector (first 4 bytes of method signature hash)
      appArgs.push(abiMethod.getSelector());
      
      // Encode arguments based on contract
      if (contract.createArgs) {
        for (let i = 0; i < contract.createArgs.length; i++) {
          const arg = contract.createArgs[i];
          const argType = createMethod.args[i].type;
          
          if (argType === 'address') {
            // Address argument - encode as 32-byte public key
            const addressValue = String(arg.value);
            appArgs.push(algosdk.decodeAddress(addressValue).publicKey);
          } else if (argType === 'asset' || argType === 'uint64') {
            // Asset ID or uint64 argument - encode as 8-byte uint64
            const encoded = new Uint8Array(8);
            const view = new DataView(encoded.buffer);
            view.setBigUint64(0, BigInt(arg.value), false);
            appArgs.push(encoded);
          }
        }
      }

      // Create application transaction
      console.log('📝 Creating application transaction...');
      const txn = algosdk.makeApplicationCreateTxnFromObject({
        sender: account.addr,
        suggestedParams: params,
        onComplete: algosdk.OnApplicationComplete.NoOpOC,
        approvalProgram: new Uint8Array(Buffer.from(approvalCompiled.result, 'base64')),
        clearProgram: new Uint8Array(Buffer.from(clearCompiled.result, 'base64')),
        numGlobalInts: contract.globalInts,
        numGlobalByteSlices: contract.globalBytes,
        numLocalInts: contract.localInts,
        numLocalByteSlices: contract.localBytes,
        appArgs,
      });

      // Sign transaction
      console.log('✍️  Signing transaction...');
      const signedTxn = txn.signTxn(account.sk);

      // Send transaction
      console.log('📤 Sending transaction to TestNet...');
      const txResponse = await algodClient.sendRawTransaction(signedTxn).do();
      const txId = txResponse.txid;
      console.log(`   Transaction ID: ${txId}`);

      // Wait for confirmation
      console.log('⏳ Waiting for confirmation...\n');
      const confirmedTxn = await algosdk.waitForConfirmation(algodClient, txId, 4);

      const appId = Number(confirmedTxn.applicationIndex || 0);
      deploymentResult.contracts[contract.name] = appId;

      console.log('✅ SUCCESS!');
      console.log(`   Contract: ${contract.name}`);
      console.log(`   App ID: ${appId}`);
      console.log(`   Explorer: https://testnet.explorer.perawallet.app/application/${appId}\n`);

    } catch (error: any) {
      console.error(`❌ Failed to deploy ${contract.name}`);
      console.error(`   Error: ${error.message}\n`);
      throw error;
    }
  }

  // Save deployment info
  const outputPath = 'deployment_testnet.json';
  fs.writeFileSync(outputPath, JSON.stringify(deploymentResult, null, 2));
  console.log('============================================================');
  console.log('📊 DEPLOYMENT SUMMARY');
  console.log('============================================================\n');
  console.log('✅ Successfully Deployed:');
  for (const [name, appId] of Object.entries(deploymentResult.contracts)) {
    console.log(`   ${name}: ${appId}`);
  }
  console.log(`\n💾 Deployment info saved to: ${outputPath}\n`);
  console.log('============================================================');
  console.log('🎉 Deployment Complete!');
  console.log('============================================================\n');
}

main().catch((error) => {
  console.error('Deployment failed:', error);
  process.exit(1);
});
