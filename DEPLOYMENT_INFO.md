# 🚀 Deployment Information

## TestNet Deployment Status: ✅ COMPLETE

**Deployed on**: April 1, 2026  
**Network**: Algorand TestNet  
**USDC Asset ID**: 10458941

---

## Deployed Contract App IDs

| Contract | App ID | Description |
|----------|--------|-------------|
| **DojoRegistry** | 758071488 | Agent identity store with Box Storage |
| **EscrowVault** | 758071501 | Per-task escrow with USDC support |
| **CommitmentLock** | 758071504 | Time-locked reputation stakes |
| **PayoutSplitter** | 758071507 | Multi-recipient USDC distribution |

---

## Verify on TestNet Explorer

- DojoRegistry: https://testnet.explorer.perawallet.app/application/758071488
- EscrowVault: https://testnet.explorer.perawallet.app/application/758071501
- CommitmentLock: https://testnet.explorer.perawallet.app/application/758071504
- PayoutSplitter: https://testnet.explorer.perawallet.app/application/758071507

---

## Deployment Configuration

**Algod Server**: https://testnet-api.algonode.cloud  
**Port**: 443  
**Network**: testnet

---

## Re-deploying or Updating

To redeploy contracts (creates new App IDs):

```bash
# Ensure .env has your mnemonic
npm run deploy
```

The deployment script (`deploy_testnet_final.ts`) will:
1. Load admin account from mnemonic
2. Connect to TestNet
3. Deploy all 4 contracts
4. Save new App IDs to `deployment_testnet.json`

---

## Integration with Backend

Use these App IDs in your backend configuration to interact with the deployed contracts.

See `README.md` for full contract documentation and method details.
