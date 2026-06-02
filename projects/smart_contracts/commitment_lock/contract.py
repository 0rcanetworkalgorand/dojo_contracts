from algopy import ARC4Contract, GlobalState, UInt64, Bytes, Txn, gtxn, itxn, Global, Account, op, urange
from algopy.arc4 import abimethod, Address, Bool, UInt64 as ARC4UInt64, String as ARC4String


class CommitmentLock(ARC4Contract):
    """Reputation Shield - Sensei stakes USDC when listing, committed for 30/60/90 days."""
    
    def __init__(self) -> None:
        self.admin = GlobalState(Account)
        self.treasury = GlobalState(Account)
        self.total_stakes = GlobalState(UInt64)
    
    @abimethod(create="require")
    def create(self, admin: Address, treasury: Address) -> None:
        """Initialize with admin and treasury address."""
        self.admin.value = admin.native
        self.treasury.value = treasury.native
        self.total_stakes.value = UInt64(0)
    
    @abimethod
    def stake(
        self,
        stake_id: ARC4String,
        sensei: Address,
        amount: ARC4UInt64,
        lock_days: ARC4UInt64,
        stake_txn: gtxn.PaymentTransaction,
    ) -> Bool:
        """Sensei stakes ALGO for 30/60/90 days."""
        assert lock_days.native == UInt64(30) or lock_days.native == UInt64(60) or lock_days.native == UInt64(90), "Invalid lock period"
        assert stake_txn.sender == sensei.native, "Sensei must send stake"
        assert stake_txn.receiver == Global.current_application_address, "Send to contract"
        assert stake_txn.amount == amount.native, "Amount mismatch"
        
        box_key = stake_id.native.bytes
        assert not op.Box.length(box_key)[1], "Stake already exists"
        
        lock_seconds = lock_days.native * UInt64(86400)
        unlock_time = Global.latest_timestamp + lock_seconds
        
        # Box format: sensei(32) + amount(8) + lock_days(8) + unlock_time(8) + withdrawn(1) = 57 bytes
        sensei_bytes = op.extract(sensei.native.bytes, 0, 32)
        amount_bytes = op.itob(amount.native)
        lock_days_bytes = op.itob(lock_days.native)
        unlock_time_bytes = op.itob(unlock_time)
        part1 = op.concat(sensei_bytes, amount_bytes)
        part2 = op.concat(lock_days_bytes, unlock_time_bytes)
        part3 = op.concat(part1, part2)
        box_data = op.concat(part3, op.bzero(1))
        op.Box.create(box_key, UInt64(57))
        op.Box.put(box_key, box_data)
        
        self.total_stakes.value += UInt64(1)
        return Bool(True)
    
    @abimethod
    def withdraw(self, stake_id: ARC4String) -> Bool:
        """Withdraw stake after lock period - clean exit returns full amount."""
        box_key = stake_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        sensei = Account(op.extract(data, 0, 32))
        amount = op.btoi(op.extract(data, 32, 8))
        unlock_time = op.btoi(op.extract(data, 48, 8))
        withdrawn = op.extract(data, 56, 1)
        
        assert Txn.sender == sensei, "Only sensei can withdraw"
        assert op.btoi(withdrawn) == UInt64(0), "Already withdrawn"
        assert Global.latest_timestamp >= unlock_time, "Still locked"
        
        # Clean exit - return full stake
        itxn.Payment(
            receiver=sensei,
            amount=amount,
        ).submit()
        
        # Mark as withdrawn
        updated = data[:56] + Bytes(b"\x01")
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod
    def release_commitment(self, stake_id: ARC4String) -> Bool:
        """Early withdrawal triggers pro-rated penalty sent to treasury."""
        box_key = stake_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        sensei = Account(op.extract(data, 0, 32))
        amount = op.btoi(op.extract(data, 32, 8))
        lock_days = op.btoi(op.extract(data, 40, 8))
        unlock_time = op.btoi(op.extract(data, 48, 8))
        withdrawn = op.extract(data, 56, 1)
        
        assert Txn.sender == sensei, "Only sensei can withdraw"
        assert op.btoi(withdrawn) == UInt64(0), "Already withdrawn"
        assert Global.latest_timestamp < unlock_time, "Lock expired, use withdraw"
        
        # Calculate pro-rated penalty
        total_lock_seconds = lock_days * UInt64(86400)
        elapsed = Global.latest_timestamp - (unlock_time - total_lock_seconds)
        remaining = unlock_time - Global.latest_timestamp
        
        # Penalty = (remaining / total) * amount
        penalty = (remaining * amount) // total_lock_seconds
        refund = amount - penalty
        
        # Send penalty to treasury
        itxn.Payment(
            receiver=self.treasury.value,
            amount=penalty,
        ).submit()
        
        # Return remaining to sensei
        itxn.Payment(
            receiver=sensei,
            amount=refund,
        ).submit()
        
        # Mark as withdrawn
        updated = data[:56] + Bytes(b"\x01")
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod
    def slash_stake(self, stake_id: ARC4String) -> Bool:
        """Admin-only: Slash a stake when an agent fails a task.
        
        Takes 10% of the staked amount and sends it to the treasury.
        The remaining 90% stays locked until the original unlock time.
        This does NOT mark the stake as withdrawn - the sensei can still
        withdraw the remaining amount after the lock period expires.
        """
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = stake_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        amount = op.btoi(op.extract(data, 32, 8))
        withdrawn = op.extract(data, 56, 1)
        
        assert op.btoi(withdrawn) == UInt64(0), "Already withdrawn"
        assert amount > UInt64(0), "No stake to slash"
        
        # Calculate 10% slash (100 basis points out of 10000)
        slash_amount = (amount * UInt64(1000)) // UInt64(10000)
        assert slash_amount > UInt64(0), "Stake too small to slash"
        
        new_amount = amount - slash_amount
        
        # Send 10% to treasury
        itxn.Payment(
            receiver=self.treasury.value,
            amount=slash_amount,
        ).submit()
        
        # Update the staked amount in box (reduce by 10%)
        updated = data[:32] + op.itob(new_amount) + data[40:]
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod(readonly=True)
    def get_stake(self, stake_id: ARC4String) -> Bytes:
        """Retrieve stake data."""
        box_key = stake_id.native.bytes
        data, _exists = op.Box.get(box_key)
        return data
    
    @abimethod(readonly=True)
    def calculate_penalty(self, stake_id: ARC4String) -> ARC4UInt64:
        """Calculate current early withdrawal penalty."""
        box_key = stake_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        amount = op.btoi(op.extract(data, 32, 8))
        lock_days = op.btoi(op.extract(data, 40, 8))
        unlock_time = op.btoi(op.extract(data, 48, 8))
        
        if Global.latest_timestamp >= unlock_time:
            return ARC4UInt64(UInt64(0))
        
        total_lock_seconds = lock_days * UInt64(86400)
        remaining = unlock_time - Global.latest_timestamp
        penalty = (remaining * amount) // total_lock_seconds
        
        return ARC4UInt64(penalty)
