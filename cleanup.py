import base64
from algosdk.v2client import algod, indexer
from algosdk import account, mnemonic, transaction
from algosdk.transaction import ApplicationDeleteTxn

def main():
    mnem = "bracket inform cricket pact impact mask misery quantum dismiss giant fog mechanic category royal east actual gold easily snow laundry vast gown crater absent denial"
    pk = mnemonic.to_private_key(mnem)
    addr = account.address_from_private_key(pk)
    print("Account:", addr)

    algod_client = algod.AlgodClient("", "https://testnet-api.algonode.cloud", "")
    idx_client = indexer.IndexerClient("", "https://testnet-idx.algonode.cloud", "")

    apps_response = idx_client.search_applications(creator=addr)
    apps = apps_response.get("applications", [])
    print(f"Found {len(apps)} apps")

    deleted = 0
    for app in apps:
        if deleted >= 5: break
        app_id = app["id"]
        print(f"Deleting app {app_id}...")
        try:
            sp = algod_client.suggested_params()
            txn = ApplicationDeleteTxn(sender=addr, sp=sp, index=app_id)
            signed = txn.sign(pk)
            txid = algod_client.send_transaction(signed)
            print(f"Sent delete tx: {txid}")
            transaction.wait_for_confirmation(algod_client, txid, 4)
            print(f"Deleted app {app_id}")
            deleted += 1
        except Exception as e:
            print(f"Failed to delete {app_id}: {e}")

if __name__ == "__main__":
    main()
