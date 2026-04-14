from algokit.core import Algorand
from algokit.core.account import Account
from algokit.core.deploy import DeployArgs, deploy as algokit_deploy
from algopy import UInt64
from algosdk import abi
from algosdk.transaction import (
    ApplicationCreateTransaction,
    ApplicationCallTransaction,
    OnComplete,
)
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)
import base64
import algosdk


def deploy(network: str, allow_update: bool):
    """Deploy contracts to Algorand."""
    print(f"Deploying to {network}")

    client = Algorand.app_client(network, "dojo-contracts")
    admin = Account.from_mnemonic(
        "bracket inform cricket pact impact mask misery quantum dismiss giant fog mechanic category royal east actual gold easily snow laundry vast gown crater absent denial"
    )

    print(f"Admin: {admin.address}")

    # Load contracts
    approval = open(
        "projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.approval.teal"
    ).read()
    clear = open(
        "projects/smart_contracts/dojo_registry/artifacts/DojoRegistry.clear.teal"
    ).read()

    print(f"Approval size: {len(approval)} bytes")

    # Deploy
    result = client.deploy(
        approval_program=approval,
        clear_program=clear,
        global_schema={"num_byte_slices": 1, "num_uints": 1},
        local_schema={"num_byte_slices": 0, "num_uints": 0},
        on_complete=OnComplete.NoOpOC,
        extra_program_pages=1,  # Allow larger contracts
    )

    print(f"App ID: {result.app_id}")
    return result


if __name__ == "__main__":
    import sys

    network = sys.argv[1] if len(sys.argv) > 1 else "testnet"
    allow_update = sys.argv[2].lower() == "true" if len(sys.argv) > 2 else False
    deploy(network, allow_update)
