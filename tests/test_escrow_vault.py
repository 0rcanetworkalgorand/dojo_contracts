import pytest
import algosdk
from algopy_testing import AlgopyTestContext, algopy_testing_context
from algopy import Account, Bytes, UInt64, op
from algopy.arc4 import Address, UInt64 as ARC4UInt64, String as ARC4String, Bool

from projects.smart_contracts.escrow_vault.contract import EscrowVault


@pytest.fixture()
def context():
    with algopy_testing_context() as ctx:
        yield ctx


@pytest.fixture()
def deployed(context: AlgopyTestContext):
    """Deploy EscrowVault and return (contract, app_id, app_address)."""
    vault = EscrowVault()
    vault.create(Address(context.default_sender))
    app_id = context.txn.last_group.txns[0].app_id
    app_address = Account(algosdk.logic.get_application_address(int(app_id.id)))
    return vault, app_id, app_address


@pytest.fixture()
def accounts(context: AlgopyTestContext):
    return {
        "client": context.any.account(),
        "worker": context.any.account(),
        "sensei": context.any.account(),
    }


def _lock_bounty(context, deployed, accounts, task_id_str="task-001", amount=1_000_000):
    """Helper: lock a bounty and return the task_id ARC4String."""
    vault, app_id, app_address = deployed
    client = accounts["client"]
    worker = accounts["worker"]
    sensei = accounts["sensei"]
    task_id = ARC4String(task_id_str)
    bounty = ARC4UInt64(amount)

    pay_txn = context.any.txn.payment(sender=client, receiver=app_address, amount=UInt64(amount))
    deferred = context.txn.defer_app_call(
        vault.lock_bounty, task_id, Address(client), Address(worker), Address(sensei), bounty, pay_txn
    )
    with context.txn.create_group([pay_txn, deferred]):
        deferred.submit()
    return task_id


class TestCreate:
    def test_create_sets_admin(self, context: AlgopyTestContext, deployed):
        vault, _, _ = deployed
        assert vault.admin.value == context.default_sender
        assert vault.total_tasks.value == UInt64(0)


class TestLockBounty:
    def test_lock_bounty_success(self, context: AlgopyTestContext, deployed, accounts):
        """Client locks a bounty — box is created with correct 137-byte structure."""
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts)

        assert vault.total_tasks.value == UInt64(1)

        # Verify box data
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert len(box_data) == 137

        # Status at offset 104 should be 0 (LOCKED)
        assert box_data[104] == 0

    def test_lock_bounty_duplicate_fails(self, context: AlgopyTestContext, deployed, accounts):
        """Cannot lock a bounty for a task_id that already exists."""
        vault, app_id, app_address = deployed
        _lock_bounty(context, deployed, accounts, task_id_str="task-dup")

        # Second attempt with same task_id should fail
        client = accounts["client"]
        worker = accounts["worker"]
        sensei = accounts["sensei"]
        task_id = ARC4String("task-dup")
        bounty = ARC4UInt64(1_000_000)
        pay_txn = context.any.txn.payment(sender=client, receiver=app_address, amount=UInt64(1_000_000))
        deferred = context.txn.defer_app_call(
            vault.lock_bounty, task_id, Address(client), Address(worker), Address(sensei), bounty, pay_txn
        )
        with pytest.raises(AssertionError, match="Task already exists"):
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()


class TestSubmitTask:
    def test_submit_task_success(self, context: AlgopyTestContext, deployed, accounts):
        """Worker submits hash — status becomes 1, kite_hash stored."""
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-sub")
        worker = accounts["worker"]
        kite_hash = Bytes(b"\xab" * 32)

        with context.txn.create_group(active_txn_overrides={"sender": worker}):
            result = vault.submit_task(task_id, kite_hash)

        assert result == Bool(True)

        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 1  # SUBMITTED
        assert box_data[105:137] == b"\xab" * 32  # kite_hash stored

    def test_submit_task_wrong_worker_fails(self, context: AlgopyTestContext, deployed, accounts):
        """Only the assigned worker can submit."""
        vault, _, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-wrong")
        impostor = context.any.account()
        kite_hash = Bytes(b"\xcd" * 32)

        with pytest.raises(AssertionError, match="Only assigned worker can submit"):
            with context.txn.create_group(active_txn_overrides={"sender": impostor}):
                vault.submit_task(task_id, kite_hash)


class TestReleasePayment:
    def _setup_submitted(self, context, deployed, accounts, task_id_str="task-rel"):
        """Lock + submit so release_payment can be tested."""
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str=task_id_str)
        worker = accounts["worker"]
        kite_hash = Bytes(b"\xef" * 32)
        with context.txn.create_group(active_txn_overrides={"sender": worker}):
            vault.submit_task(task_id, kite_hash)
        return task_id

    def test_release_by_client(self, context: AlgopyTestContext, deployed, accounts):
        """Client can sign release_payment — trustless on-chain settlement."""
        vault, app_id, _ = deployed
        task_id = self._setup_submitted(context, deployed, accounts, "task-client-rel")
        client = accounts["client"]
        treasury = context.any.account()

        with context.txn.create_group(active_txn_overrides={"sender": client}):
            result = vault.release_payment(task_id, Address(treasury))

        assert result == Bool(True)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 2  # COMPLETED

    def test_release_by_admin(self, context: AlgopyTestContext, deployed, accounts):
        """Admin can also release — convenience for automated flows."""
        vault, app_id, _ = deployed
        task_id = self._setup_submitted(context, deployed, accounts, "task-admin-rel")
        admin = context.default_sender
        treasury = context.any.account()

        with context.txn.create_group(active_txn_overrides={"sender": admin}):
            result = vault.release_payment(task_id, Address(treasury))

        assert result == Bool(True)

    def test_release_requires_submitted(self, context: AlgopyTestContext, deployed, accounts):
        """Cannot release if task hasn't been submitted (still LOCKED)."""
        vault, _, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-notsub")
        client = accounts["client"]
        treasury = context.any.account()

        with pytest.raises(AssertionError, match="Task must be submitted"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.release_payment(task_id, Address(treasury))

    def test_release_unauthorized_fails(self, context: AlgopyTestContext, deployed, accounts):
        """Random address cannot release — must be client or admin."""
        vault, _, _ = deployed
        task_id = self._setup_submitted(context, deployed, accounts, "task-unauth")
        random_user = context.any.account()
        treasury = context.any.account()

        with pytest.raises(AssertionError, match="Only client or admin"):
            with context.txn.create_group(active_txn_overrides={"sender": random_user}):
                vault.release_payment(task_id, Address(treasury))


class TestSlashBounty:
    def test_slash_by_client(self, context: AlgopyTestContext, deployed, accounts):
        """Client can slash (refund) directly — trustless refund."""
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-slash-c")
        client = accounts["client"]

        with context.txn.create_group(active_txn_overrides={"sender": client}):
            result = vault.slash_bounty(task_id)

        assert result == Bool(True)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 3  # SLASHED

    def test_slash_by_admin(self, context: AlgopyTestContext, deployed, accounts):
        """Admin can slash on behalf of client."""
        vault, _, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-slash-a")
        admin = context.default_sender

        with context.txn.create_group(active_txn_overrides={"sender": admin}):
            result = vault.slash_bounty(task_id)

        assert result == Bool(True)

    def test_slash_unauthorized_fails(self, context: AlgopyTestContext, deployed, accounts):
        """Random user cannot slash."""
        vault, _, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-slash-u")
        random_user = context.any.account()

        with pytest.raises(AssertionError, match="Only client or admin"):
            with context.txn.create_group(active_txn_overrides={"sender": random_user}):
                vault.slash_bounty(task_id)

    def test_slash_already_settled_fails(self, context: AlgopyTestContext, deployed, accounts):
        """Cannot slash a task that's already been slashed."""
        vault, _, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-double")
        client = accounts["client"]

        with context.txn.create_group(active_txn_overrides={"sender": client}):
            vault.slash_bounty(task_id)

        with pytest.raises(AssertionError, match="Already settled"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.slash_bounty(task_id)
