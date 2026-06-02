import pytest
import algosdk
from algopy_testing import AlgopyTestContext, algopy_testing_context
from algopy import Account, Bytes, UInt64, op
from algopy.arc4 import Address, UInt64 as ARC4UInt64, String as ARC4String, Bool

from projects.smart_contracts.commitment_lock.contract import CommitmentLock


@pytest.fixture()
def context():
    with algopy_testing_context() as ctx:
        yield ctx


@pytest.fixture()
def treasury(context: AlgopyTestContext):
    return context.any.account()


@pytest.fixture()
def deployed(context: AlgopyTestContext, treasury):
    """Deploy CommitmentLock and return (contract, app_id, app_address)."""
    lock = CommitmentLock()
    lock.create(Address(context.default_sender), Address(treasury))
    app_id = context.txn.last_group.txns[0].app_id
    app_address = Account(algosdk.logic.get_application_address(int(app_id.id)))
    return lock, app_id, app_address


@pytest.fixture()
def sensei(context: AlgopyTestContext):
    return context.any.account()


def _stake(context, deployed, sensei, stake_id_str="stake-001", amount=5_000_000, days=30):
    """Helper: create a stake and return the stake_id."""
    lock, app_id, app_address = deployed
    stake_id = ARC4String(stake_id_str)
    amt = ARC4UInt64(amount)
    lock_days = ARC4UInt64(days)

    pay_txn = context.any.txn.payment(sender=sensei, receiver=app_address, amount=UInt64(amount))
    deferred = context.txn.defer_app_call(
        lock.stake, stake_id, Address(sensei), amt, lock_days, pay_txn
    )
    with context.txn.create_group([pay_txn, deferred]):
        deferred.submit()
    return stake_id


class TestCreate:
    def test_create_sets_admin_and_treasury(self, context: AlgopyTestContext, deployed, treasury):
        lock, _, _ = deployed
        assert lock.admin.value == context.default_sender
        assert lock.treasury.value == treasury
        assert lock.total_stakes.value == UInt64(0)


class TestStake:
    def test_stake_30_days(self, context: AlgopyTestContext, deployed, sensei):
        """30-day stake creates a 57-byte box with correct data."""
        lock, app_id, _ = deployed
        stake_id = _stake(context, deployed, sensei, "stake-30", days=30)

        assert lock.total_stakes.value == UInt64(1)
        box_data = context.ledger.get_box(app_id, stake_id.native.bytes)
        assert len(box_data) == 57
        # withdrawn flag at offset 56 should be 0
        assert box_data[56] == 0

    def test_stake_60_days(self, context: AlgopyTestContext, deployed, sensei):
        """60-day lock period is accepted."""
        lock, app_id, _ = deployed
        stake_id = _stake(context, deployed, sensei, "stake-60", days=60)
        assert lock.total_stakes.value == UInt64(1)

    def test_stake_90_days(self, context: AlgopyTestContext, deployed, sensei):
        """90-day lock period is accepted."""
        lock, app_id, _ = deployed
        stake_id = _stake(context, deployed, sensei, "stake-90", days=90)
        assert lock.total_stakes.value == UInt64(1)

    def test_stake_invalid_period_fails(self, context: AlgopyTestContext, deployed, sensei):
        """Lock period must be 30, 60, or 90."""
        lock, app_id, app_address = deployed
        stake_id = ARC4String("stake-bad")
        amt = ARC4UInt64(1_000_000)
        lock_days = ARC4UInt64(45)

        pay_txn = context.any.txn.payment(sender=sensei, receiver=app_address, amount=UInt64(1_000_000))
        deferred = context.txn.defer_app_call(lock.stake, stake_id, Address(sensei), amt, lock_days, pay_txn)
        with pytest.raises(AssertionError, match="Invalid lock period"):
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()

    def test_stake_duplicate_fails(self, context: AlgopyTestContext, deployed, sensei):
        """Cannot create a stake with the same ID twice."""
        lock, app_id, app_address = deployed
        _stake(context, deployed, sensei, "stake-dup", days=30)

        stake_id = ARC4String("stake-dup")
        amt = ARC4UInt64(1_000_000)
        lock_days = ARC4UInt64(30)
        pay_txn = context.any.txn.payment(sender=sensei, receiver=app_address, amount=UInt64(1_000_000))
        deferred = context.txn.defer_app_call(lock.stake, stake_id, Address(sensei), amt, lock_days, pay_txn)
        with pytest.raises(AssertionError, match="Stake already exists"):
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()


class TestSlashStake:
    def test_slash_reduces_amount(self, context: AlgopyTestContext, deployed, sensei):
        """Admin slashes 10% — box amount decreases, not marked withdrawn."""
        lock, app_id, _ = deployed
        stake_id = _stake(context, deployed, sensei, "stake-slash", amount=10_000_000)
        admin = context.default_sender

        with context.txn.create_group(active_txn_overrides={"sender": admin}):
            result = lock.slash_stake(stake_id)

        assert result == Bool(True)

        box_data = context.ledger.get_box(app_id, stake_id.native.bytes)
        # Amount at offset 32 should be 9M (10M - 10%)
        stored_amount = int.from_bytes(box_data[32:40], "big")
        assert stored_amount == 9_000_000
        # Not marked as withdrawn
        assert box_data[56] == 0

    def test_slash_non_admin_fails(self, context: AlgopyTestContext, deployed, sensei):
        """Only admin can slash a stake."""
        lock, _, _ = deployed
        stake_id = _stake(context, deployed, sensei, "stake-nonadmin")

        with pytest.raises(AssertionError, match="Only admin"):
            with context.txn.create_group(active_txn_overrides={"sender": sensei}):
                lock.slash_stake(stake_id)

    def test_slash_already_withdrawn_fails(self, context: AlgopyTestContext, deployed, sensei):
        """Cannot slash a stake that has been withdrawn."""
        lock, app_id, _ = deployed
        stake_id = _stake(context, deployed, sensei, "stake-wd", amount=5_000_000)

        # Manually mark as withdrawn
        box_data = context.ledger.get_box(app_id, stake_id.native.bytes)
        updated = box_data[:56] + b"\x01"
        context.ledger.set_box(app_id, stake_id.native.bytes, updated)

        admin = context.default_sender
        with pytest.raises(AssertionError, match="Already withdrawn"):
            with context.txn.create_group(active_txn_overrides={"sender": admin}):
                lock.slash_stake(stake_id)
