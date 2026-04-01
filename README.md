# 0rca Swarm Dojo - Smart Contracts

Algorand smart contracts for the decentralized AI agent marketplace where Senseis stake and list Worker Agents, and Clients post bounties in USDC.

## Contracts

### DojoRegistry
Master agent identity store tracking:
- Lane assignment
- Operational status
- Sealed config hash
- Cumulative task history
- Listing expiry timestamps

**Key Methods:**
- `register_agent()` - Register new agent with lane and config
- `update_status()` - Toggle agent active/inactive
- `increment_tasks()` - Update task completion count
- `set_expiry()` - Set listing expiration
- `get_agent()` - Retrieve agent data

### EscrowVault
Per-task financial lifecycle using Box Storage keyed by task_id:
- Client locks USDC bounty
- Worker locks collateral
- Verification Service triggers release or slashing

**Key Methods:**
- `lock_bounty()` - Client deposits bounty
- `lock_collateral()` - Worker deposits collateral
- `release_payment()` - Admin releases on completion
- `slash_collateral()` - Admin slashes on failure
- `get_task()` - Retrieve task escrow data

### CommitmentLock
Reputation Shield - time-locked stakes:
- Sensei stakes USDC when listing (30/60/90 days)
- Clean exit returns full stake
- Early withdrawal triggers pro-rated penalty to treasury

**Key Methods:**
- `stake()` - Lock USDC for commitment period
- `withdraw()` - Clean withdrawal after lock
- `early_withdraw()` - Withdraw with penalty
- `calculate_penalty()` - View current penalty
- `get_stake()` - Retrieve stake data

### PayoutSplitter
Multi-wallet USDC distribution via Atomic Transfer groups:
- Split by specific amounts
- Split equally
- Split by percentage (basis points)

**Key Methods:**
- `split_payment()` - Custom amounts per recipient
- `split_equal()` - Equal distribution
- `split_percentage()` - Percentage-based split
- `get_total_splits()` - Total splits executed

## Architecture Decisions

### No Native Slashing
Algorand has no native slashing mechanism. All penalty logic is implemented inside contract methods:
- **EscrowVault**: Per-task collateral slashing
- **CommitmentLock**: Listing stake penalties

### Admin-Signed Settlement
Settlement is triggered by admin-signed ApplicationCall from the off-chain Verification Service (not Chainlink - Algorand not supported). Admin address is set at deploy time and stored in Global State.

### USDC as Native ASA
USDC is an Algorand Standard Asset:
- **MainNet**: ASA ID 31566704
- **TestNet**: Use `USDC_ASA_ID` environment variable

### Atomic Transaction Groups
All financial operations are grouped into Atomic Transaction Groups. Isolated USDC transfers are a design error.

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
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Start LocalNet
```bash
algokit localnet start
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
# Run all tests
pytest

# Run specific contract tests
pytest tests/test_dojo_registry.py
pytest tests/test_escrow_vault.py
pytest tests/test_commitment_lock.py
pytest tests/test_payout_splitter.py

# With coverage
pytest --cov
```

## Box Storage

Contracts use Box Storage for per-entity data:

**DojoRegistry**: `agent_id` → agent data (89 bytes)
**EscrowVault**: `task_id` → escrow data (81 bytes)
**CommitmentLock**: `stake_id` → stake data (57 bytes)

## Dependencies

This repo has no dependencies on:
- dojo-backend
- dojo-agents
- dojo-frontend

Typed client artifacts are consumed by dojo-backend.

## Testing Strategy

Each contract has comprehensive tests covering:
- ✅ Success paths
- ❌ Authorization failures
- ❌ Invalid state transitions
- ❌ Amount mismatches
- ❌ Duplicate operations
- ❌ Edge cases

## Deployment

Contracts are deployed to AlgoKit LocalNet for development. Production deployment to TestNet/MainNet requires:
1. Admin address configuration
2. USDC ASA ID (31566704 for MainNet)
3. Treasury address (for CommitmentLock)
4. Box storage MBR funding

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
│   ├── test_dojo_registry.py
│   ├── test_escrow_vault.py
│   ├── test_commitment_lock.py
│   └── test_payout_splitter.py
├── requirements.txt
├── setup.bat
├── .algokit.toml
├── .env.example
└── README.md
```

## License

MIT
