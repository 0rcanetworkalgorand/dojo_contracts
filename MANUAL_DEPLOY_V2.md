# Manual Deployment - DojoRegistry (Fixed)

## Contract is Ready
- **Approval**: `projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal` (~17KB)
- **Clear**: `projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal`

## Steps in Pera Wallet (Mobile)

1. Open **Pera Wallet** → Go to **Apps** → **Deploy App**

2. Upload TEAL files:
   - Approval Program: `DojoRegistry.approval.teal`
   - Clear Program: `DojoRegistry.clear.teal`

3. Configure:
   - **Global Ints**: 1
   - **Global Bytes**: 1  
   - **Local Ints**: 0
   - **Local Bytes**: 0
   - **Extra Pages**: **4** (Maximum - needed for ~17KB contract)

4. App Arguments (Raw Bytes):
   - arg[0]: `637265617465` (hex for "create")
   - arg[1]: `574f4c4652494b365451335a3441483755554a593339584553583541493736474a5252343751574f5a423658494f5743564a4347364e4d45` (hex for admin address)

5. Click **Deploy**

6. **Save the App ID** from the transaction result

## Your Admin Address
```
BSOIH3B7JSKWKLWTFHLUE3KMKFU4WQBHEEEICBFG226HEUSMTPDISHV4ZM
```

## After Deployment
Once you have the new App ID, I'll update:
- `dojo-backend/.env` → DOJO_REGISTRY_APP_ID
- `dojo-frontend/.env.local` → NEXT_PUBLIC_DOJO_REGISTRY_APP_ID

Then test agent deployment from the frontend.

## If Pera Also Fails
The contract needs to be simplified (reduce functionality). Let me know the error and we'll go that route.