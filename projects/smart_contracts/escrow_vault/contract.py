from algopy import ARC4Contract, GlobalState, UInt64, Bytes, Txn, gtxn, Asset, itxn, Global, Account, op, urange
from algopy.arc4 import abimethod, Address, Bool, UInt64 as ARC4UInt64, String as ARC4String


class EscrowVault(ARC4Contract):
    """Per-task escrow managing USDC bounty and collateral with Box Storage keyed by task_id."""
    
    def __init__(self) -> None:
        self.admin = GlobalState(Account)
        self.usdc_asset_id = GlobalState(UInt64)
        self.total_tasks = GlobalState(UInt64)
    
    @abimethod(create="require")
    def create(self, admin: Address, usdc_asset: Asset) -> None:
        """Initialize vault with admin and USDC ASA ID."""
        self.admin.value = admin.native
        self.usdc_asset_id.value = usdc_asset.id
        self.total_tasks.value = UInt64(0)
    
    @abimethod
    def lock_bounty(
        self,
        task_id: ARC4String,
        client: Address,
        worker: Address,
        bounty_amount: ARC4UInt64,
        collateral_amount: ARC4UInt64,
        bounty_txn: gtxn.AssetTransferTransaction,
    ) -> Bool:
        """Client locks USDC bounty for a task."""
        assert bounty_txn.sender == client.native, "Client must send bounty"
        assert bounty_txn.asset_receiver == Global.current_application_address, "Send to contract"
        assert bounty_txn.xfer_asset == Asset(self.usdc_asset_id.value), "Must be USDC"
        assert bounty_txn.asset_amount == bounty_amount.native, "Amount mismatch"
        
        box_key = task_id.native.bytes
        assert not op.Box.length(box_key), "Task already exists"
        
        # Box format: client(32) + worker(32) + bounty(8) + collateral(8) + status(1) = 81 bytes
        # status: 0=locked, 1=completed, 2=slashed
        client_bytes = op.extract(client.native.bytes, 0, 32)
        worker_bytes = op.extract(worker.native.bytes, 0, 32)
        bounty_bytes = op.itob(bounty_amount.native)
        collateral_bytes = op.itob(collateral_amount.native)
        part1 = op.concat(client_bytes, worker_bytes)
        part2 = op.concat(bounty_bytes, collateral_bytes)
        part3 = op.concat(part1, part2)
        box_data = op.concat(part3, op.bzero(1))
        op.Box.create(box_key, UInt64(81))
        op.Box.put(box_key, box_data)
        
        self.total_tasks.value += UInt64(1)
        return Bool(True)
    
    @abimethod
    def lock_collateral(
        self,
        task_id: ARC4String,
        collateral_txn: gtxn.AssetTransferTransaction,
    ) -> Bool:
        """Worker locks USDC collateral."""
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        worker = Account(op.extract(data, 32, 32))
        collateral_amount = op.btoi(op.extract(data, 72, 8))
        
        assert collateral_txn.sender == worker, "Worker must send collateral"
        assert collateral_txn.asset_receiver == Global.current_application_address, "Send to contract"
        assert collateral_txn.xfer_asset == Asset(self.usdc_asset_id.value), "Must be USDC"
        assert collateral_txn.asset_amount == collateral_amount, "Amount mismatch"
        
        return Bool(True)
    
    @abimethod
    def release_payment(self, task_id: ARC4String) -> Bool:
        """Admin releases bounty to worker on validated completion."""
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        worker = Account(op.extract(data, 32, 32))
        bounty = op.btoi(op.extract(data, 64, 8))
        collateral = op.btoi(op.extract(data, 72, 8))
        status = op.extract(data, 80, 1)
        
        assert op.btoi(status) == UInt64(0), "Already settled"
        
        # Release bounty + collateral to worker
        total_payment = bounty + collateral
        itxn.AssetTransfer(
            xfer_asset=Asset(self.usdc_asset_id.value),
            asset_receiver=worker,
            asset_amount=total_payment,
        ).submit()
        
        # Update status to completed
        updated = data[:80] + Bytes(b"\x01")
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod
    def slash_collateral(self, task_id: ARC4String, treasury: Address) -> Bool:
        """Admin slashes collateral on failure, returns bounty to client."""
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        client = Account(op.extract(data, 0, 32))
        bounty = op.btoi(op.extract(data, 64, 8))
        collateral = op.btoi(op.extract(data, 72, 8))
        status = op.extract(data, 80, 1)
        
        assert op.btoi(status) == UInt64(0), "Already settled"
        
        # Return bounty to client
        itxn.AssetTransfer(
            xfer_asset=Asset(self.usdc_asset_id.value),
            asset_receiver=client,
            asset_amount=bounty,
        ).submit()
        
        # Send collateral to treasury
        itxn.AssetTransfer(
            xfer_asset=Asset(self.usdc_asset_id.value),
            asset_receiver=treasury.native,
            asset_amount=collateral,
        ).submit()
        
        # Update status to slashed
        updated = data[:80] + Bytes(b"\x02")
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod(readonly=True)
    def get_task(self, task_id: ARC4String) -> Bytes:
        """Retrieve task escrow data."""
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        return data
