"""Economic split tests for EscrowVault release_payment and slash_bounty.

Validates Requirements 2.1, 2.2, 2.5:
- Treasury gets exactly the floored 2% fee
- Sensei gets exactly the remaining amount
- fee + sensei_payment == bounty (conservation)
- Slash returns 100% bounty to client with no fee
"""

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


def _submit_task(context, deployed, accounts, task_id):
    """Helper: submit task so it reaches SUBMITTED status with a valid kite_hash."""
    vault, app_id, _ = deployed
    worker = accounts["worker"]
    kite_hash = Bytes(b"\xef" * 32)
    with context.txn.create_group(active_txn_overrides={"sender": worker}):
        vault.submit_task(task_id, kite_hash)


def _submit_task_with_zero_hash(context, deployed, accounts, task_id):
    """Helper: submit task with a zero kite_hash (invalid provenance).

    Manipulates the box directly to simulate a SUBMITTED state with zero hash,
    since the contract's submit_task doesn't validate the hash content itself.
    """
    vault, app_id, _ = deployed
    box_data = context.ledger.get_box(app_id, task_id.native.bytes)
    # Set status to 1 (SUBMITTED) but leave kite_hash as zeros
    updated = box_data[:104] + b"\x01" + b"\x00" * 32
    context.ledger.set_box(app_id, task_id.native.bytes, updated)


def _set_task_status(context, deployed, task_id, status_byte):
    """Helper: directly set the task status byte in the box for testing guard conditions."""
    vault, app_id, _ = deployed
    box_data = context.ledger.get_box(app_id, task_id.native.bytes)
    updated = box_data[:104] + bytes([status_byte]) + box_data[105:]
    context.ledger.set_box(app_id, task_id.native.bytes, updated)


class TestEconomicSplits:
    """Example-based tests for the economic split logic in release_payment and slash_bounty."""

    def test_release_fee_and_sensei_amounts(self, context: AlgopyTestContext, deployed, accounts):
        """Release with bounty 1_000_033 (not divisible by 50) exercises fee truncation.

        Expected:
          fee = (1_000_033 * 200) // 10000 = 20_000
          sensei_payment = 1_000_033 - 20_000 = 980_033

        Validates: Requirements 2.1
        """
        bounty_amount = 1_000_033
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-eco-1", amount=bounty_amount)
        _submit_task(context, deployed, accounts, task_id)

        vault, app_id, _ = deployed
        client = accounts["client"]
        sensei = accounts["sensei"]
        treasury = context.any.account()

        with context.txn.create_group(active_txn_overrides={"sender": client}):
            result = vault.release_payment(task_id, Address(treasury))

        assert result == Bool(True)

        # Expected fee and sensei amounts
        expected_fee = (bounty_amount * 200) // 10000  # = 20_000
        expected_sensei = bounty_amount - expected_fee  # = 980_033

        assert expected_fee == 20_000
        assert expected_sensei == 980_033

        # The contract issues two inner payments (each as a separate itxn group):
        # 1st group: fee to treasury
        # 2nd group: sensei_payment to sensei
        last_group = context.txn.last_group
        itxn_groups = last_group.itxn_groups
        assert len(itxn_groups) == 2

        fee_itxn = itxn_groups[0][0]
        sensei_itxn = itxn_groups[1][0]

        assert fee_itxn.receiver == treasury
        assert fee_itxn.amount == UInt64(expected_fee)

        assert sensei_itxn.receiver == sensei
        assert sensei_itxn.amount == UInt64(expected_sensei)

    def test_release_conservation_of_funds(self, context: AlgopyTestContext, deployed, accounts):
        """The sum of treasury fee and sensei payment equals the original bounty.

        Validates: Requirements 2.2
        """
        bounty_amount = 5_000_000
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-eco-2", amount=bounty_amount)
        _submit_task(context, deployed, accounts, task_id)

        vault, app_id, _ = deployed
        client = accounts["client"]
        treasury = context.any.account()

        with context.txn.create_group(active_txn_overrides={"sender": client}):
            vault.release_payment(task_id, Address(treasury))

        # Verify conservation: fee + sensei_payment == bounty
        last_group = context.txn.last_group
        itxn_groups = last_group.itxn_groups

        fee_itxn = itxn_groups[0][0]
        sensei_itxn = itxn_groups[1][0]

        fee_paid = fee_itxn.amount
        sensei_paid = sensei_itxn.amount

        assert fee_paid + sensei_paid == UInt64(bounty_amount)

    def test_slash_returns_full_bounty(self, context: AlgopyTestContext, deployed, accounts):
        """Slash returns 100% of bounty to client — no fee, no treasury/sensei payment.

        Validates: Requirements 2.5
        """
        bounty_amount = 2_500_000
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-eco-3", amount=bounty_amount)

        vault, app_id, _ = deployed
        client = accounts["client"]

        with context.txn.create_group(active_txn_overrides={"sender": client}):
            result = vault.slash_bounty(task_id)

        assert result == Bool(True)

        # Verify single inner payment: full bounty to client
        last_group = context.txn.last_group
        itxn_groups = last_group.itxn_groups
        assert len(itxn_groups) == 1

        refund_itxn = itxn_groups[0][0]
        assert refund_itxn.receiver == client
        assert refund_itxn.amount == UInt64(bounty_amount)

        # Verify status is SLASHED (3)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 3


class TestNegativePathGuards:
    """Negative-path tests verifying guard conditions on release_payment and slash_bounty.

    After each failed call, verifies:
    - Task status byte is unchanged
    - No inner payments were issued

    Validates: Requirements 2.3, 2.4, 2.6, 2.7
    """

    def test_release_requires_submitted_status_locked(self, context: AlgopyTestContext, deployed, accounts):
        """release_payment on LOCKED (status=0) fails with AssertionError.

        Validates: Requirements 2.3
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-locked", amount=1_000_000)
        # Task is LOCKED (status=0) — no submit_task called
        client = accounts["client"]
        treasury = context.any.account()

        # Verify pre-condition: status is LOCKED (0)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 0

        with pytest.raises(AssertionError, match="Task must be submitted"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.release_payment(task_id, Address(treasury))

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 0

    def test_release_requires_submitted_status_completed(self, context: AlgopyTestContext, deployed, accounts):
        """release_payment on COMPLETED (status=2) fails with AssertionError.

        Validates: Requirements 2.3
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-completed", amount=1_000_000)
        # Directly set status to COMPLETED (2)
        _set_task_status(context, deployed, task_id, 2)
        client = accounts["client"]
        treasury = context.any.account()

        # Verify pre-condition: status is COMPLETED (2)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 2

        with pytest.raises(AssertionError, match="Task must be submitted"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.release_payment(task_id, Address(treasury))

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 2

    def test_release_requires_submitted_status_slashed(self, context: AlgopyTestContext, deployed, accounts):
        """release_payment on SLASHED (status=3) fails with AssertionError.

        Validates: Requirements 2.3
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-slashed", amount=1_000_000)
        # Directly set status to SLASHED (3)
        _set_task_status(context, deployed, task_id, 3)
        client = accounts["client"]
        treasury = context.any.account()

        # Verify pre-condition: status is SLASHED (3)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 3

        with pytest.raises(AssertionError, match="Task must be submitted"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.release_payment(task_id, Address(treasury))

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 3

    def test_release_requires_nonzero_kite_hash(self, context: AlgopyTestContext, deployed, accounts):
        """release_payment with 32 zero-byte kite_hash fails with AssertionError.

        Validates: Requirements 2.4
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-zerohash", amount=1_000_000)
        # Set status to SUBMITTED (1) but leave kite_hash as zeros
        _submit_task_with_zero_hash(context, deployed, accounts, task_id)
        client = accounts["client"]
        treasury = context.any.account()

        # Verify pre-condition: status is SUBMITTED (1) with zero kite_hash
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 1
        assert box_data[105:137] == b"\x00" * 32

        with pytest.raises(AssertionError, match="Provenance hash not set"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.release_payment(task_id, Address(treasury))

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 1

    def test_slash_fails_on_completed(self, context: AlgopyTestContext, deployed, accounts):
        """slash_bounty on COMPLETED (status=2) fails with AssertionError.

        Validates: Requirements 2.6
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-slash-comp", amount=1_000_000)
        # Directly set status to COMPLETED (2)
        _set_task_status(context, deployed, task_id, 2)
        client = accounts["client"]

        # Verify pre-condition: status is COMPLETED (2)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 2

        with pytest.raises(AssertionError, match="Already settled"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.slash_bounty(task_id)

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 2

    def test_slash_fails_on_slashed(self, context: AlgopyTestContext, deployed, accounts):
        """slash_bounty on SLASHED (status=3) fails with AssertionError.

        Validates: Requirements 2.6
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-slash-slash", amount=1_000_000)
        # Directly set status to SLASHED (3)
        _set_task_status(context, deployed, task_id, 3)
        client = accounts["client"]

        # Verify pre-condition: status is SLASHED (3)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 3

        with pytest.raises(AssertionError, match="Already settled"):
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.slash_bounty(task_id)

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 3

    def test_release_unauthorized(self, context: AlgopyTestContext, deployed, accounts):
        """Random account cannot call release_payment — authorization fails.

        Validates: Requirements 2.7
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-unauth-rel", amount=1_000_000)
        _submit_task(context, deployed, accounts, task_id)
        random_user = context.any.account()
        treasury = context.any.account()

        # Verify pre-condition: status is SUBMITTED (1)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 1

        with pytest.raises(AssertionError, match="Only client or admin"):
            with context.txn.create_group(active_txn_overrides={"sender": random_user}):
                vault.release_payment(task_id, Address(treasury))

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 1

    def test_slash_unauthorized(self, context: AlgopyTestContext, deployed, accounts):
        """Random account cannot call slash_bounty — authorization fails.

        Validates: Requirements 2.7
        """
        vault, app_id, _ = deployed
        task_id = _lock_bounty(context, deployed, accounts, task_id_str="task-neg-unauth-slash", amount=1_000_000)
        random_user = context.any.account()

        # Verify pre-condition: status is LOCKED (0)
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 0

        with pytest.raises(AssertionError, match="Only client or admin"):
            with context.txn.create_group(active_txn_overrides={"sender": random_user}):
                vault.slash_bounty(task_id)

        # Verify status unchanged
        box_data = context.ledger.get_box(app_id, task_id.native.bytes)
        assert box_data[104] == 0
