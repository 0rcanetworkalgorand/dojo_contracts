# Manual Deployment Instructions for DojoRegistry (Fixed)

## Contract Issue
The compiled DojoRegistry contract is ~17KB (fixed version), which exceeds Algorand's default program size limits. The current mainnet/testnet apps can use up to 10KB but can request up to 28KB with extra pages.

## Files Ready
- Approval Program: `projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal`
- Clear Program: `projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal`

## Steps to Deploy via Pera Wallet (or other wallet)

### Step 1: Open Pera Wallet
1. Open your Pera Wallet browser extension/app
2. Ensure you're connected to TestNet

### Step 2: Deploy the App
1. Go to Apps → Deploy App
2. Select the two TEAL files:
   - **Approval Program**: Load `DojoRegistry.approval.teal`
   - **Clear Program**: Load `DojoRegistry.clear.teal`
3. Set the following:
   - **Global Ints**: 1
   - **Global ByteSlices**: 1
   - **Local Ints**: 0
   - **Byte Slices**: 0
   - **Extra Pages**: Request 3 (to allow 17KB+ contract)
4. In the app arguments, add:
   - arg[0]: "create" (method selector)
   - arg[1]: `WOLFRIK6TQ3Z4QH7UJJY3XESX5AI76GJRRHO47QWOZB6XIOWCQVJCG6NME` (admin address)
5. Click Deploy

### Step 3: Note the New App ID
Once deployed, copy the new **App ID** from the transaction result.

### Step 4: Update Environment Files
Update both `.env` files with the new App ID:

**dojo-backend/.env:**
```
DOJO_REGISTRY_APP_ID=<NEW_APP_ID>
```

**dojo-frontend/.env.local:**
```
NEXT_PUBLIC_DOJO_REGISTRY_APP_ID=<NEW_APP_ID>
```

### Step 5: Restart Backend
Restart the dojo-backend server to pick up the new contract ID.

## If Pera Also Rejects

The contract may still be too large. In that case, we need to simplify. Contact me with the error and we can either:

1. Remove unused methods temporarily to reduce size
2. Split the contract into multiple contracts
3. Wait for Algorand's larger program limit upgrade

## Verification
After deployment and backend restart, test agent registration:
```bash
curl -X POST http://localhost:3001/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agentId":"TEST_001","senseiAddress":"WOLFRIK6TQ3Z4QH7UJJY3XESX5AI76GJRRHO47QWOZB6XIOWCQVJCG6NME","lane":"RESEARCH","llmTier":"Standard","biddingStrategy":"Volume","openaiApiKey":"sk-testkey12345678901234567890"}'
```