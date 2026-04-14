#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

load_dotenv()

import algosdk
from algosdk.v2client import algod
from algosdk.transaction import ApplicationCreateTransaction, OnComplete
from algosdk import wait_for_confirmation

# Load mnemonic from .env
mnemonic = os.getenv("ADMIN_PASSPHRASE")
account = algosdk.mnemonic_to_secret_key(mnemonic)
admin_address = account.addr
print(f"Admin: {admin_address}")

# Load contracts
approval = open(
    "projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal"
).read()
clear = open(
    "projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal"
).read()
print(f"Approval TEAL size: {len(approval)} bytes")

# Create client
algod_token = os.getenv("ALGOD_TOKEN", "")
algod_server = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
algod_port = os.getenv("ALGOD_PORT", "443")

client = algod.AlgodClient(algod_token, f"{algod_server}:{algod_port}")

# Get account info
acct_info = client.account_info(admin_address)
balance = acct_info.get("amount", 0) / 1e6
print(f"Balance: {balance:.4f} ALGO")

# Get suggested params
params = client.suggested_params()
params.fee = 20000  # Higher fee for large contract
params.flat_fee = True

# TEAL is text, encode to bytes
app_args = [admin_address.encode()]

txn = ApplicationCreateTransaction(
    sender=admin_address,
    sp=params,
    on_complete=OnComplete.NoOpOC,
    approval_program=approval.encode(),
    clear_program=clear.encode(),
    global_schema={"num_byte_slices": 1, "num_uints": 1},
    local_schema={"num_byte_slices": 0, "num_uints": 0},
    extra_pages=1,  # Allow larger contract
    app_args=app_args,
)

# Sign
signed = txn.sign(account.private_key)

# Send
tx_id = client.send_transaction(signed)
print(f"Transaction ID: {tx_id}")

# Wait for confirmation
confirmed = wait_for_confirmation(client, tx_id, timeout=10)
app_id = confirmed.get("application-index")
print(f"\n=== SUCCESS ===")
print(f"New App ID: {app_id}")
print(f"\nUpdate .env with: DOJO_REGISTRY_APP_ID={app_id}")
