# Deployment to TestNet

## Your Wallet
Please ensure your Pera Wallet (address: `BSOIH3B7JSKWKLWTFHLUE3KMKFU4WQBHEEEICBFG226HEUSMTPDISHV4ZM`) is connected to TestNet and funded.

## Contract Files
- Approval: `projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal` (~17KB, fixed version)
- Clear: `projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal`

## Steps in Pera Wallet

1. Open Pera Wallet → Apps → Deploy App

2. Upload:
   - **Approval Program**: `DojoRegistry.approval.teal`
   - **Clear Program**: `DojoRegistry.clear.teal`

3. Configure:
   - **Global Ints**: 1
   - **Global Bytes**: 1
   - **Local Ints**: 0
   - **Local Bytes**: 0
   - **Extra Pages**: 3 (required for ~17KB contract)

4. App Args (Raw):
   - Paste these as hex or raw bytes:
   ```
   637265617465  (method: "create")
   ```
   - Then add your admin address as a 32-byte application argument

5. Click Deploy

6. **Save the App ID** from the transaction result.

## After Deployment

I will update the .env files with the new App ID. Please share:
- DojoRegistry App ID
- Any other contract App IDs you deploy

## Test
After updating .env, restart backend and test registration.