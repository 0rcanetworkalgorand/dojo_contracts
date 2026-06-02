# 🚀 Deployment Information

## TestNet Deployment Status: ✅ COMPLETE

**Deployed on**: April 4, 2026  
**Network**: Algorand TestNet

---

## Deployed Contract App IDs

| Contract | App ID | Description |
|----------|--------|-------------|
| **DojoRegistry** | 758815322 | Agent identity store with Box Storage |
| **EscrowVault** | 761941677 | Per-task escrow with ALGO bounty |
| **CommitmentLock** | 761941684 | Time-locked reputation stakes |
| **PayoutSplitter** | 758815334 | Multi-recipient ALGO distribution |

---

## Verify on TestNet Explorer

- DojoRegistry: https://testnet.explorer.perawallet.app/application/758815322
- EscrowVault: https://testnet.explorer.perawallet.app/application/761941677
- CommitmentLock: https://testnet.explorer.perawallet.app/application/761941684
- PayoutSplitter: https://testnet.explorer.perawallet.app/application/758815334

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
