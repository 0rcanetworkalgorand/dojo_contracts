from algopy import ARC4Contract, GlobalState, UInt64, Bytes, Txn, gtxn, Asset, itxn, Global, Account, op, urange
from algopy.arc4 import abimethod, Address, Bool, UInt64 as ARC4UInt64, String as ARC4String


class EscrowVault(ARC4Contract):
    """Per-task escrow managing USDC bounty and collateral with Box Storage keyed by task_id."""
    
    def __init__(self) -> None:
        self.admin = GlobalState(Account)
        self.total_tasks = GlobalState(UInt64)
    
    @abimethod(create="require")
    def create(self, admin: Address) -> None:
        """Initialize vault with admin."""
        self.admin.value = admin.native
        self.total_tasks.value = UInt64(0)
    
    @abimethod
    def lock_bounty(
        self,
        task_id: ARC4String,
        client: Address,
        worker: Address,
        bounty_amount: ARC4UInt64,
        collateral_amount: ARC4UInt64,
        bounty_txn: gtxn.PaymentTransaction,
    ) -> Bool:
        """Client locks ALGO bounty for a task."""
        assert bounty_txn.sender == client.native, "Client must send bounty"
        assert bounty_txn.receiver == Global.current_application_address, "Send to contract"
        assert bounty_txn.amount == bounty_amount.native, "Amount mismatch"
        
        box_key = task_id.native.bytes
        assert not op.Box.length(box_key)[1], "Task already exists"
        
        # Box format: client(32) + worker(32) + bounty(8) + collateral(8) + status(1) + kite_hash(32) = 113 bytes
        # status: 0=locked, 1=submitted, 2=completed, 3=slashed
        client_bytes = op.extract(client.native.bytes, 0, 32)
        worker_bytes = op.extract(worker.native.bytes, 0, 32)
        bounty_bytes = op.itob(bounty_amount.native)
        collateral_bytes = op.itob(collateral_amount.native)
        part1 = op.concat(client_bytes, worker_bytes)
        part2 = op.concat(bounty_bytes, collateral_bytes)
        part3 = op.concat(part1, part2)
        # Add status (0) and placeholder for hash
        box_data = op.concat(part3, op.bzero(33))
        op.Box.create(box_key, UInt64(113))
        op.Box.put(box_key, box_data)
        
        self.total_tasks.value += UInt64(1)
        return Bool(True)

    @abimethod
    def lock_collateral(
        self,
        task_id: ARC4String,
        collateral_txn: gtxn.PaymentTransaction,
    ) -> Bool:
        """Worker locks ALGO collateral."""
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        worker = Account(op.extract(data, 32, 32))
        collateral_amount = op.btoi(op.extract(data, 72, 8))
        
        assert collateral_txn.sender == worker, "Worker must send collateral"
        assert collateral_txn.receiver == Global.current_application_address, "Send to contract"
        assert collateral_txn.amount == collateral_amount, "Amount mismatch"
        
        return Bool(True)

    @abimethod
    def submit_task(self, task_id: ARC4String, kite_hash: Bytes) -> Bool:
        """Worker submits the task result with Kite AI provenance hash."""
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        worker = Account(op.extract(data, 32, 32))
        status = op.extract(data, 80, 1)
        
        assert Txn.sender == worker, "Only assigned worker can submit"
        assert op.btoi(status) == UInt64(0), "Task not in lock state"
        # assert kite_hash.length == UInt64(32), "Invalid hash length"
        
        # Update status to 1 (SUBMITTED) and store hash
        updated = data[:80] + Bytes(b"\x01") + kite_hash
        op.Box.put(box_key, updated)
        return Bool(True)
    
    @abimethod
    def release_payment(self, task_id: ARC4String, treasury: Address) -> Bool:
        """Admin releases bounty to worker on validated completion with 2% platform fee calculation."""
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        worker = Account(op.extract(data, 32, 32))
        bounty = op.btoi(op.extract(data, 64, 8))
        collateral = op.btoi(op.extract(data, 72, 8))
        status = op.extract(data, 80, 1)
        
        # Can be settled from locked (0) or submitted (1)
        assert op.btoi(status) <= UInt64(1), "Already settled or slashed"
        
        # Calculate 2% platform fee
        fee = (bounty * UInt64(200)) // UInt64(10000)
        worker_bounty = bounty - fee
        total_worker_payment = worker_bounty + collateral
        
        # 1. Release fee to treasury
        itxn.Payment(
            receiver=treasury.native,
            amount=fee,
        ).submit()
        
        # 2. Release bounty + collateral to worker
        itxn.Payment(
            receiver=worker,
            amount=total_worker_payment,
        ).submit()
        
        # Update status to 2 (COMPLETED)
        updated = data[:80] + Bytes(b"\x02") + data[81:]
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod
    def slash_collateral(self, task_id: ARC4String, treasury: Address) -> Bool:
        """Admin slashes collateral on failure, returns bounty to client and collateral to treasury."""
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        client = Account(op.extract(data, 0, 32))
        bounty = op.btoi(op.extract(data, 64, 8))
        collateral = op.btoi(op.extract(data, 72, 8))
        status = op.extract(data, 80, 1)
        
        assert op.btoi(status) <= UInt64(1), "Already settled"
        
        # 1. Return Bounty to client (Full refund)
        itxn.Payment(
            receiver=client,
            amount=bounty,
        ).submit()

        # 2. Send Slashed Collateral to Treasury (Platform Owner)
        itxn.Payment(
            receiver=treasury.native,
            amount=collateral,
        ).submit()
        
        # Update status to 3 (SLASHED)
        updated = data[:80] + Bytes(b"\x03") + data[81:]
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod(readonly=True)
    def get_task(self, task_id: ARC4String) -> Bytes:
        """Retrieve task escrow data."""
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        return data
