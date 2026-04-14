import base64
from algosdk.v2client import algod, indexer
from algosdk import account, mnemonic, transaction

def main():
    mnem = "bracket inform cricket pact impact mask misery quantum dismiss giant fog mechanic category royal east actual gold easily snow laundry vast gown crater absent denial"
    pk = mnemonic.to_private_key(mnem)
    addr = account.address_from_private_key(pk)
    print("Account:", addr)

    algod_client = algod.AlgodClient("", "https://testnet-api.algonode.cloud", "")
    info = algod_client.account_info(addr)
    assets = info.get("assets", [])
    print(f"Found {len(assets)} assets")

    for asset in assets:
        asset_id = asset["asset-id"]
        print(f"Opting out of asset {asset_id}...")
        try:
            sp = algod_client.suggested_params()
            txn = transaction.AssetTransferTxn(
                sender=addr,
                sp=sp,
                receiver=addr,
                amt=0,
                index=asset_id,
                close_assets_to=addr  # Close out to self, or creator. Actually creator of asset!
            )
            # Actually, to close out of an asset, close_assets_to must be the creator. But wait, we can just send it with close_assets_to=creator.
            # Let's get creator:
            asset_info = algod_client.asset_info(asset_id)
            creator = asset_info["params"]["creator"]
            
            txn = transaction.AssetTransferTxn(
                sender=addr,
                sp=sp,
                receiver=creator,
                amt=0,
                index=asset_id,
                close_assets_to=creator
            )
            signed = txn.sign(pk)
            txid = algod_client.send_transaction(signed)
            print(f"Sent close out tx: {txid}")
            transaction.wait_for_confirmation(algod_client, txid, 4)
            print(f"Closed out of asset {asset_id}")
        except Exception as e:
            print(f"Failed to opt out {asset_id}: {e}")

if __name__ == "__main__":
    main()
