import pytest
import algosdk
from algopy_testing import AlgopyTestContext, algopy_testing_context
from algopy import Account, Bytes, UInt64
from algopy.arc4 import Address, UInt64 as ARC4UInt64, Bool, DynamicArray

from projects.smart_contracts.payout_splitter.contract import PayoutSplitter


@pytest.fixture()
def context():
    with algopy_testing_context() as ctx:
        yield ctx


@pytest.fixture()
def deployed(context: AlgopyTestContext):
    """Deploy PayoutSplitter and return (contract, app_id, app_address)."""
    splitter = PayoutSplitter()
    splitter.create(Address(context.default_sender))
    app_id = context.txn.last_group.txns[0].app_id
    app_address = Account(algosdk.logic.get_application_address(int(app_id.id)))
    return splitter, app_id, app_address


class TestCreate:
    def test_create_sets_admin(self, context: AlgopyTestContext, deployed):
        splitter, _, _ = deployed
        assert splitter.admin.value == context.default_sender
        assert splitter.total_splits.value == UInt64(0)


class TestSplitPayment:
    def test_split_two_recipients(self, context: AlgopyTestContext, deployed):
        """Split payment across 2 recipients with specified amounts."""
        splitter, _, app_address = deployed
        recipient_a = context.any.account()
        recipient_b = context.any.account()

        recipients = DynamicArray[Address](Address(recipient_a), Address(recipient_b))
        amounts = DynamicArray[ARC4UInt64](ARC4UInt64(700_000), ARC4UInt64(300_000))

        pay_txn = context.any.txn.payment(
            sender=context.default_sender, receiver=app_address, amount=UInt64(1_000_000)
        )
        deferred = context.txn.defer_app_call(splitter.split_payment, recipients, amounts, pay_txn)
        with context.txn.create_group([pay_txn, deferred]):
            result = deferred.submit()

        assert result == Bool(True)
        assert splitter.total_splits.value == UInt64(1)

    def test_split_amount_mismatch_fails(self, context: AlgopyTestContext, deployed):
        """Payment amount must equal sum of specified amounts."""
        splitter, _, app_address = deployed
        recipient_a = context.any.account()

        recipients = DynamicArray[Address](Address(recipient_a))
        amounts = DynamicArray[ARC4UInt64](ARC4UInt64(500_000))

        # Pay 1M but amounts only sum to 500k
        pay_txn = context.any.txn.payment(
            sender=context.default_sender, receiver=app_address, amount=UInt64(1_000_000)
        )
        deferred = context.txn.defer_app_call(splitter.split_payment, recipients, amounts, pay_txn)
        with pytest.raises(AssertionError, match="Payment amount mismatch"):
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()


class TestSplitPercentage:
    def test_split_percentage_success(self, context: AlgopyTestContext, deployed):
        """Split by percentage (70%/30%) — must sum to 10000 basis points."""
        splitter, _, app_address = deployed
        recipient_a = context.any.account()
        recipient_b = context.any.account()

        recipients = DynamicArray[Address](Address(recipient_a), Address(recipient_b))
        percentages = DynamicArray[ARC4UInt64](ARC4UInt64(7000), ARC4UInt64(3000))

        pay_txn = context.any.txn.payment(
            sender=context.default_sender, receiver=app_address, amount=UInt64(2_000_000)
        )
        deferred = context.txn.defer_app_call(splitter.split_percentage, recipients, percentages, pay_txn)
        with context.txn.create_group([pay_txn, deferred]):
            result = deferred.submit()

        assert result == Bool(True)
        assert splitter.total_splits.value == UInt64(1)

    def test_split_percentage_not_100_fails(self, context: AlgopyTestContext, deployed):
        """Percentages must sum to exactly 10000 (100%)."""
        splitter, _, app_address = deployed
        recipient_a = context.any.account()
        recipient_b = context.any.account()

        recipients = DynamicArray[Address](Address(recipient_a), Address(recipient_b))
        percentages = DynamicArray[ARC4UInt64](ARC4UInt64(5000), ARC4UInt64(4000))  # = 9000

        pay_txn = context.any.txn.payment(
            sender=context.default_sender, receiver=app_address, amount=UInt64(1_000_000)
        )
        deferred = context.txn.defer_app_call(splitter.split_percentage, recipients, percentages, pay_txn)
        with pytest.raises(AssertionError, match="Percentages must sum to 100%"):
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()
