#!/bin/bash
# Deploy large contract via REST API

ALGOD="https://testnet-api.algonode.cloud"
MNEMONIC="bracket inform cricket pact impact mask misery quantum dismiss giant fog mechanic category royal east actual gold easily snow laundry vast gown crater absent denial"

# Get admin address
ADMIN=$(python3 -c "import algosdk; print(algosdk.mnemonic_to_address('$MNEMONIC'))")
echo "Admin: $ADMIN"

# Load contracts
APPROVAL=$(cat projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal | base64 -w0)
CLEAR=$(cat projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal | base64 -w0)
echo "Approval size: $(($(wc -c < projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal)/1024))KB"

# Get params
PARAMS=$(curl -s -X GET "$ALGOD/v2/transactions/params" -H "Content-Type: application/json")
echo "Params: $PARAMS"