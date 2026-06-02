from algopy import ARC4Contract, GlobalState, UInt64, Bytes, Txn, gtxn, itxn, Global, Account, op, urange
from algopy.arc4 import abimethod, Address, Bool, UInt64 as ARC4UInt64, DynamicArray


class PayoutSplitter(ARC4Contract):
    """Distributes USDC earnings across multiple worker wallets using Atomic Transfer groups."""
    
    def __init__(self) -> None:
        self.admin = GlobalState(Account)
        self.total_splits = GlobalState(UInt64)
    
    @abimethod(create="require")
    def create(self, admin: Address) -> None:
        """Initialize with admin."""
        self.admin.value = admin.native
        self.total_splits.value = UInt64(0)
    
    @abimethod
    def split_payment(
        self,
        recipients: DynamicArray[Address],
        amounts: DynamicArray[ARC4UInt64],
        payment_txn: gtxn.PaymentTransaction,
    ) -> Bool:
        """Split ALGO payment across multiple recipients in atomic group."""
        assert recipients.length == amounts.length, "Recipients and amounts length mismatch"
        assert recipients.length > UInt64(0), "No recipients"
        assert recipients.length <= UInt64(16), "Max 16 recipients per split"
        
        # Verify payment transaction
        assert payment_txn.receiver == Global.current_application_address, "Send to contract"
        
        # Calculate total and verify
        total = UInt64(0)
        for i in urange(recipients.length):
            total += amounts[i].native
        
        assert payment_txn.amount == total, "Payment amount mismatch"
        
        # Execute atomic transfers to all recipients
        for i in urange(recipients.length):
            itxn.Payment(
                receiver=recipients[i].native,
                amount=amounts[i].native,
            ).submit()
        
        self.total_splits.value += UInt64(1)
        return Bool(True)
    
    @abimethod
    def split_equal(
        self,
        recipients: DynamicArray[Address],
        payment_txn: gtxn.PaymentTransaction,
    ) -> Bool:
        """Split ALGO payment equally across recipients."""
        assert recipients.length > UInt64(0), "No recipients"
        assert recipients.length <= UInt64(16), "Max 16 recipients"
        
        assert payment_txn.receiver == Global.current_application_address, "Send to contract"
        
        total_amount = payment_txn.amount
        per_recipient = total_amount // recipients.length
        remainder = total_amount % recipients.length
        
        # Send equal amounts to all recipients
        for i in urange(recipients.length):
            amount = per_recipient
            # Give remainder to first recipient
            if i == UInt64(0):
                amount += remainder
            
            itxn.Payment(
                receiver=recipients[i].native,
                amount=amount,
            ).submit()
        
        self.total_splits.value += UInt64(1)
        return Bool(True)
    
    @abimethod
    def split_percentage(
        self,
        recipients: DynamicArray[Address],
        percentages: DynamicArray[ARC4UInt64],
        payment_txn: gtxn.PaymentTransaction,
    ) -> Bool:
        """Split ALGO by percentage (basis points: 10000 = 100%)."""
        assert recipients.length == percentages.length, "Length mismatch"
        assert recipients.length > UInt64(0), "No recipients"
        assert recipients.length <= UInt64(16), "Max 16 recipients"
        
        assert payment_txn.receiver == Global.current_application_address, "Send to contract"
        
        # Verify percentages sum to 10000 (100%)
        total_percentage = UInt64(0)
        for i in urange(percentages.length):
            total_percentage += percentages[i].native
        assert total_percentage == UInt64(10000), "Percentages must sum to 100%"
        
        total_amount = payment_txn.amount
        distributed = UInt64(0)
        
        # Distribute based on percentages
        for i in urange(recipients.length):
            if i == recipients.length - UInt64(1):
                # Last recipient gets remainder to handle rounding
                amount = total_amount - distributed
            else:
                amount = (total_amount * percentages[i].native) // UInt64(10000)
                distributed += amount
            
            itxn.Payment(
                receiver=recipients[i].native,
                amount=amount,
            ).submit()
        
        self.total_splits.value += UInt64(1)
        return Bool(True)
    
    @abimethod(readonly=True)
    def get_total_splits(self) -> ARC4UInt64:
        """Get total number of splits executed."""
        return ARC4UInt64(self.total_splits.value)
