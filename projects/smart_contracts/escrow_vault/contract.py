from algopy import ARC4Contract, GlobalState, UInt64, Bytes, Txn, gtxn, Asset, itxn, Global, Account, op, urange
from algopy.arc4 import abimethod, Address, Bool, UInt64 as ARC4UInt64, String as ARC4String


class EscrowVault(ARC4Contract):
    """Per-task escrow managing ALGO bounty with Box Storage keyed by task_id.
    
    On success: 2% platform fee to treasury, 98% to sensei (developer).
    On failure: 100% bounty refunded to client (user).
    """
    
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
        sensei: Address,
        bounty_amount: ARC4UInt64,
        bounty_txn: gtxn.PaymentTransaction,
    ) -> Bool:
        """Client locks ALGO bounty for a task.
        
        Args:
            task_id: Unique task identifier
            client: The user who is paying for the task
            worker: The agent address assigned to the task
            sensei: The developer who deployed the agent (receives 98% on success)
            bounty_amount: Amount of ALGO bounty in microAlgos
            bounty_txn: The payment transaction sending ALGO to this contract
        """
        assert bounty_txn.sender == client.native, "Client must send bounty"
        assert bounty_txn.receiver == Global.current_application_address, "Send to contract"
        assert bounty_txn.amount == bounty_amount.native, "Amount mismatch"
        
        box_key = task_id.native.bytes
        assert not op.Box.length(box_key)[1], "Task already exists"
        
        # Box format: client(32) + worker(32) + sensei(32) + bounty(8) + status(1) + kite_hash(32) = 137 bytes
        # status: 0=locked, 1=submitted, 2=completed, 3=slashed
        client_bytes = op.extract(client.native.bytes, 0, 32)
        worker_bytes = op.extract(worker.native.bytes, 0, 32)
        sensei_bytes = op.extract(sensei.native.bytes, 0, 32)
        bounty_bytes = op.itob(bounty_amount.native)
        part1 = op.concat(client_bytes, worker_bytes)
        part2 = op.concat(part1, sensei_bytes)
        part3 = op.concat(part2, bounty_bytes)
        # Add status (0) and placeholder for hash
        box_data = op.concat(part3, op.bzero(33))
        op.Box.create(box_key, UInt64(137))
        op.Box.put(box_key, box_data)
        
        self.total_tasks.value += UInt64(1)
        return Bool(True)

    @abimethod
    def submit_task(self, task_id: ARC4String, kite_hash: Bytes) -> Bool:
        """Worker submits the task result with Kite AI provenance hash."""
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        worker = Account(op.extract(data, 32, 32))
        status = op.extract(data, 104, 1)
        
        assert Txn.sender == worker, "Only assigned worker can submit"
        assert op.btoi(status) == UInt64(0), "Task not in lock state"
        
        # Update status to 1 (SUBMITTED) and store hash
        updated = data[:104] + Bytes(b"\x01") + kite_hash
        op.Box.put(box_key, updated)
        return Bool(True)
    
    @abimethod
    def release_payment(self, task_id: ARC4String, treasury: Address) -> Bool:
        """Admin releases bounty on validated completion.
        
        Distribution: 2% platform fee to treasury, 98% to sensei (developer) directly.
        """
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        sensei = Account(op.extract(data, 64, 32))
        bounty = op.btoi(op.extract(data, 96, 8))
        status = op.extract(data, 104, 1)
        
        # Can be settled from locked (0) or submitted (1)
        assert op.btoi(status) <= UInt64(1), "Already settled or slashed"
        
        # Calculate 2% platform fee
        fee = (bounty * UInt64(200)) // UInt64(10000)
        sensei_payment = bounty - fee
        
        # 1. Release 2% fee to treasury
        itxn.Payment(
            receiver=treasury.native,
            amount=fee,
        ).submit()
        
        # 2. Release 98% to sensei (developer) directly
        itxn.Payment(
            receiver=sensei,
            amount=sensei_payment,
        ).submit()
        
        # Update status to 2 (COMPLETED)
        updated = data[:104] + Bytes(b"\x02") + data[105:]
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod
    def slash_bounty(self, task_id: ARC4String) -> Bool:
        """Admin slashes on task failure - returns 100% bounty to client (user).
        
        No platform fee on the bounty side. The 1% developer slash is handled
        separately by the CommitmentLock contract.
        """
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        client = Account(op.extract(data, 0, 32))
        bounty = op.btoi(op.extract(data, 96, 8))
        status = op.extract(data, 104, 1)
        
        assert op.btoi(status) <= UInt64(1), "Already settled"
        
        # Return 100% bounty to client (user) - no deductions
        itxn.Payment(
            receiver=client,
            amount=bounty,
        ).submit()
        
        # Update status to 3 (SLASHED)
        updated = data[:104] + Bytes(b"\x03") + data[105:]
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod(readonly=True)
    def get_task(self, task_id: ARC4String) -> Bytes:
        """Retrieve task escrow data."""
        box_key = task_id.native.bytes
        data, _exists = op.Box.get(box_key)
        return data
