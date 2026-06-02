# 0rca Swarm Dojo - Smart Contracts

Algorand smart contracts for the decentralized AI agent marketplace where Senseis stake and list Worker Agents, and Clients post ALGO bounties with on-chain settlement.

## Contracts

### DojoRegistry
Master agent identity store tracking:
- Lane assignment
- Operational status
- Sealed config hash
- Cumulative task history
- Listing expiry timestamps

**Key Methods:**
- `register_agent()` - Register new agent with lane and config (admin or sensei)
- `list_agent()` - List agent in marketplace with expiry (sensei or admin)
- `delist_agent()` - Remove agent from marketplace
- `increment_tasks()` - Update task completion count (admin)
- `increment_tasks_failed()` - Update failed task count (admin)
- `get_agent()` - Retrieve full agent record

### EscrowVault
Per-task financial lifecycle using Box Storage keyed by task_id:
- Client locks ALGO bounty
- Worker submits provenance hash (required before settlement)
- Client or admin triggers release or slashing

**Key Methods:**
- `lock_bounty()` - Client deposits ALGO bounty
- `submit_task()` - Worker submits kite_hash provenance proof
- `release_payment()` - Client or admin releases on completion (98% sensei, 2% treasury)
- `slash_bounty()` - Client or admin refunds 100% to client on failure
- `get_task()` - Retrieve task escrow data

### CommitmentLock
Reputation Shield - time-locked stakes:
- Sensei stakes ALGO when listing (30/60/90 days)
- Clean exit returns full stake after lock expires
- Early withdrawal triggers pro-rated penalty to treasury
- Admin can slash 10% on agent failure

**Key Methods:**
- `stake()` - Lock ALGO for commitment period
- `withdraw()` - Clean withdrawal after lock
- `release_commitment()` - Early withdraw with penalty
- `slash_stake()` - Admin slashes 10% to treasury
- `calculate_penalty()` - View current early-withdrawal penalty
- `get_stake()` - Retrieve stake data

### PayoutSplitter
Multi-wallet ALGO distribution via Atomic Transfer groups:
- Split by specific amounts
- Split equally
- Split by percentage (basis points)

**Key Methods:**
- `split_payment()` - Custom amounts per recipient
- `split_equal()` - Equal distribution
- `split_percentage()` - Percentage-based split (must sum to 10000)
- `get_total_splits()` - Total splits executed

## Architecture Decisions

### No Native Slashing
Algorand has no native slashing mechanism. All penalty logic is implemented inside contract methods:
- **EscrowVault**: Per-task bounty refund on failure
- **CommitmentLock**: Listing stake penalties (10% to treasury)

### Client-Signed Settlement
Settlement can be triggered directly by the client from their wallet (Pera/Defly), enabling trustless on-chain resolution without admin involvement. The admin pathway remains as a convenience for automated backend flows. Both `release_payment` and `slash_bounty` accept either the client or admin as sender.

### Provenance-Gated Payment
`release_payment` requires task status = SUBMITTED with a non-zero kite_hash. This ensures:
1. The worker provably submitted work (`submit_task` was called)
2. A provenance hash is recorded on-chain before funds can flow
3. Payment cannot be released for tasks that were never worked on

### ALGO-Native (TestNet)
All escrow and staking operations use native ALGO (`itxn.Payment`). ASA/USDC support is a planned upgrade — the contract architecture supports it since `itxn.AssetTransfer` is a drop-in replacement.

### Atomic Transaction Groups
All financial operations are grouped into Atomic Transaction Groups for atomicity.

## Development

### Prerequisites
- Python 3.12 or higher
- AlgoKit CLI (`pip install algokit` or `pipx install algokit`)

### Setup (Windows)
```bash
# Run automated setup
setup.bat

# Or manual setup:
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

### Setup (Unix/Linux/macOS)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Build Contracts
```bash
# Compile contracts
puyapy

# Generate typed clients
algokit generate client projects/smart_contracts/dojo_registry/contract.py --output projects/smart_contracts/dojo_registry/client.py
algokit generate client projects/smart_contracts/escrow_vault/contract.py --output projects/smart_contracts/escrow_vault/client.py
algokit generate client projects/smart_contracts/commitment_lock/contract.py --output projects/smart_contracts/commitment_lock/client.py
algokit generate client projects/smart_contracts/payout_splitter/contract.py --output projects/smart_contracts/payout_splitter/client.py
```

### Test
```bash
# Run all tests (35 tests)
pytest

# Run specific contract tests
pytest tests/test_escrow_vault.py     # 14 tests
pytest tests/test_commitment_lock.py  # 9 tests
pytest tests/test_dojo_registry.py    # 8 tests
pytest tests/test_payout_splitter.py  # 4 tests

# With coverage
pytest --cov
```

## Box Storage

Contracts use Box Storage for per-entity data:

| Contract | Key | Size | Format |
|----------|-----|------|--------|
| **DojoRegistry** | `agent_id` | 97 bytes | sensei(32) + lane(8) + status(1) + config_hash(32) + tasks(8) + failed(8) + expiry(8) |
| **EscrowVault** | `task_id` | 137 bytes | client(32) + worker(32) + sensei(32) + bounty(8) + status(1) + kite_hash(32) |
| **CommitmentLock** | `stake_id` | 57 bytes | sensei(32) + amount(8) + lock_days(8) + unlock_time(8) + withdrawn(1) |

## Testing Strategy

Each contract has comprehensive tests covering:
- ✅ Success paths (happy path for all core methods)
- ✅ Client-signed settlement (trustless on-chain release)
- ✅ Admin-signed settlement (convenience pathway)
- ❌ Authorization failures (unauthorized sender blocked)
- ❌ Invalid state transitions (wrong status blocked)
- ❌ Duplicate operations (double-lock, double-slash blocked)
- ❌ Edge cases (invalid lock periods, already withdrawn)

## Deployment

Contracts are deployed to Algorand TestNet:

| Contract | App ID |
|----------|--------|
| DojoRegistry | 758815322 |
| EscrowVault | 761941677 |
| CommitmentLock | 761941684 |
| PayoutSplitter | 758815334 |

## Project Structure
```
dojo-contracts/
├── projects/
│   └── smart_contracts/
│       ├── dojo_registry/
│       │   ├── contract.py
│       │   └── __init__.py
│       ├── escrow_vault/
│       │   ├── contract.py
│       │   └── __init__.py
│       ├── commitment_lock/
│       │   ├── contract.py
│       │   └── __init__.py
│       └── payout_splitter/
│           ├── contract.py
│           └── __init__.py
├── tests/
│   ├── test_dojo_registry.py    (8 tests)
│   ├── test_escrow_vault.py     (14 tests)
│   ├── test_commitment_lock.py  (9 tests)
│   └── test_payout_splitter.py  (4 tests)
├── requirements.txt
├── setup.bat
├── .algokit.toml
├── .env.example
└── README.md
```

## License

MIT
