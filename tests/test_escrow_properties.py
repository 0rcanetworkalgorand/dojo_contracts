"""Property-based tests for EscrowVault economic invariants using Hypothesis.

Validates Requirements 3.1, 3.2, 3.5:
- Conservation of funds: fee + sensei_payment == bounty for all bounty amounts
- Fee formula correctness: fee == (bounty * 200) // 10000, sensei_payment == bounty - fee
- Boundary values exercised: 1, 49, 50, 51, MAX_SAFE_BOUNTY
- At least 200 examples per property

Also includes Property 3 (release guard) and Property 4 (slash full refund).

Note: The contract computes `bounty * UInt64(200)` which overflows uint64 when
bounty > (2^64-1)//200. The safe maximum bounty is therefore (2^64-1)//200 =
92_233_720_368_547_758. This is the effective contract limit — values above this
would revert on-chain with an overflow. We test up to this boundary.
"""

import pytest
import algosdk
from hypothesis import given, settings, example
from hypothesis import strategies as st

from algopy_testing import AlgopyTestContext, algopy_testing_context
from algopy import Account, Bytes, UInt64, op
from algopy.arc4 import Address, UInt64 as ARC4UInt64, String as ARC4String, Bool

from projects.smart_contracts.escrow_vault.contract import EscrowVault

# The contract computes fee = (bounty * 200) // 10000. Since bounty * 200 must
# fit in a uint64 (AVM arithmetic), the effective max bounty is (2^64-1) // 200.
MAX_SAFE_BOUNTY = (2**64 - 1) // 200  # 92_233_720_368_547_758


# ---------- Fixtures ----------

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


# ---------- Helpers ----------

_task_counter = 0


def _unique_task_id():
    """Generate a unique task ID for each hypothesis example to avoid box collisions."""
    global _task_counter
    _task_counter += 1
    return f"prop-task-{_task_counter}"


def _lock_bounty(context, deployed, accounts, task_id_str, amount):
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


def _set_task_status(context, deployed, task_id, status_byte):
    """Helper: directly set the task status byte in the box for testing guard conditions."""
    vault, app_id, _ = deployed
    box_data = context.ledger.get_box(app_id, task_id.native.bytes)
    updated = box_data[:104] + bytes([status_byte]) + box_data[105:]
    context.ledger.set_box(app_id, task_id.native.bytes, updated)


def _submit_task_with_zero_hash(context, deployed, task_id):
    """Helper: set status to SUBMITTED but leave kite_hash as zeros."""
    vault, app_id, _ = deployed
    box_data = context.ledger.get_box(app_id, task_id.native.bytes)
    updated = box_data[:104] + b"\x01" + b"\x00" * 32
    context.ledger.set_box(app_id, task_id.native.bytes, updated)


# ---------- Property Tests ----------


class TestFeeFormulaProperties:
    """Property-based tests for EscrowVault economic invariants."""

    # Feature: semifinal-hardening, Property 1: Fee formula correctness
    @given(bounty=st.integers(min_value=1, max_value=MAX_SAFE_BOUNTY))
    @settings(max_examples=200)
    @example(bounty=1)
    @example(bounty=49)
    @example(bounty=50)
    @example(bounty=51)
    @example(bounty=MAX_SAFE_BOUNTY)
    def test_fee_formula_correctness(self, bounty):
        """For any bounty in [1, 2^64-1], fee == (bounty * 200) // 10000
        and sensei_payment == bounty - fee.

        **Validates: Requirements 3.2**
        """
        # Feature: semifinal-hardening, Property 1: Fee formula correctness
        with algopy_testing_context() as context:
            # Deploy
            vault = EscrowVault()
            vault.create(Address(context.default_sender))
            app_id = context.txn.last_group.txns[0].app_id
            app_address = Account(algosdk.logic.get_application_address(int(app_id.id)))

            # Accounts
            client = context.any.account()
            worker = context.any.account()
            sensei = context.any.account()
            treasury = context.any.account()

            # Lock bounty
            task_id_str = _unique_task_id()
            task_id = ARC4String(task_id_str)
            pay_txn = context.any.txn.payment(sender=client, receiver=app_address, amount=UInt64(bounty))
            deferred = context.txn.defer_app_call(
                vault.lock_bounty, task_id, Address(client), Address(worker),
                Address(sensei), ARC4UInt64(bounty), pay_txn
            )
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()

            # Submit task
            kite_hash = Bytes(b"\xef" * 32)
            with context.txn.create_group(active_txn_overrides={"sender": worker}):
                vault.submit_task(task_id, kite_hash)

            # Release payment
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.release_payment(task_id, Address(treasury))

            # Extract inner transaction amounts
            last_group = context.txn.last_group
            itxn_groups = last_group.itxn_groups
            fee_itxn = itxn_groups[0][0]
            sensei_itxn = itxn_groups[1][0]

            actual_fee = int(fee_itxn.amount)
            actual_sensei = int(sensei_itxn.amount)

            # Assert Property 1: fee formula correctness
            expected_fee = (bounty * 200) // 10000
            expected_sensei = bounty - expected_fee

            assert actual_fee == expected_fee, (
                f"Fee mismatch: got {actual_fee}, expected {expected_fee} for bounty={bounty}"
            )
            assert actual_sensei == expected_sensei, (
                f"Sensei mismatch: got {actual_sensei}, expected {expected_sensei} for bounty={bounty}"
            )

    # Feature: semifinal-hardening, Property 2: Conservation of funds on release
    @given(bounty=st.integers(min_value=1, max_value=MAX_SAFE_BOUNTY))
    @settings(max_examples=200)
    @example(bounty=1)
    @example(bounty=49)
    @example(bounty=50)
    @example(bounty=51)
    @example(bounty=MAX_SAFE_BOUNTY)
    def test_conservation_of_funds_on_release(self, bounty):
        """For any bounty in [1, 2^64-1], fee + sensei_payment == bounty.

        **Validates: Requirements 3.1**
        """
        # Feature: semifinal-hardening, Property 2: Conservation of funds on release
        with algopy_testing_context() as context:
            # Deploy
            vault = EscrowVault()
            vault.create(Address(context.default_sender))
            app_id = context.txn.last_group.txns[0].app_id
            app_address = Account(algosdk.logic.get_application_address(int(app_id.id)))

            # Accounts
            client = context.any.account()
            worker = context.any.account()
            sensei = context.any.account()
            treasury = context.any.account()

            # Lock bounty
            task_id_str = _unique_task_id()
            task_id = ARC4String(task_id_str)
            pay_txn = context.any.txn.payment(sender=client, receiver=app_address, amount=UInt64(bounty))
            deferred = context.txn.defer_app_call(
                vault.lock_bounty, task_id, Address(client), Address(worker),
                Address(sensei), ARC4UInt64(bounty), pay_txn
            )
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()

            # Submit task
            kite_hash = Bytes(b"\xef" * 32)
            with context.txn.create_group(active_txn_overrides={"sender": worker}):
                vault.submit_task(task_id, kite_hash)

            # Release payment
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.release_payment(task_id, Address(treasury))

            # Extract inner transaction amounts
            last_group = context.txn.last_group
            itxn_groups = last_group.itxn_groups
            fee_itxn = itxn_groups[0][0]
            sensei_itxn = itxn_groups[1][0]

            actual_fee = int(fee_itxn.amount)
            actual_sensei = int(sensei_itxn.amount)

            # Assert Property 2: conservation of funds
            assert actual_fee + actual_sensei == bounty, (
                f"Conservation violated: {actual_fee} + {actual_sensei} = {actual_fee + actual_sensei} != {bounty}"
            )

    # Feature: semifinal-hardening, Property 3: Release guard — no payout without valid preconditions
    @given(bounty=st.integers(min_value=1, max_value=MAX_SAFE_BOUNTY))
    @settings(max_examples=200)
    @example(bounty=1)
    @example(bounty=49)
    @example(bounty=50)
    @example(bounty=51)
    @example(bounty=MAX_SAFE_BOUNTY)
    def test_release_guard_no_payout_without_preconditions(self, bounty):
        """For any task where status != SUBMITTED or kite_hash is zero,
        release_payment fails with AssertionError and status remains unchanged.

        **Validates: Requirements 2.3, 2.4, 3.4**
        """
        # Feature: semifinal-hardening, Property 3: Release guard — no payout without valid preconditions
        with algopy_testing_context() as context:
            # Deploy
            vault = EscrowVault()
            vault.create(Address(context.default_sender))
            app_id = context.txn.last_group.txns[0].app_id
            app_address = Account(algosdk.logic.get_application_address(int(app_id.id)))

            # Accounts
            client = context.any.account()
            worker = context.any.account()
            sensei = context.any.account()
            treasury = context.any.account()

            # Lock bounty (status=LOCKED=0)
            task_id_str = _unique_task_id()
            task_id = ARC4String(task_id_str)
            pay_txn = context.any.txn.payment(sender=client, receiver=app_address, amount=UInt64(bounty))
            deferred = context.txn.defer_app_call(
                vault.lock_bounty, task_id, Address(client), Address(worker),
                Address(sensei), ARC4UInt64(bounty), pay_txn
            )
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()

            # Case 1: status=LOCKED (0) — release should fail
            box_data = context.ledger.get_box(app_id, task_id.native.bytes)
            assert box_data[104] == 0  # pre-condition check

            with pytest.raises(AssertionError):
                with context.txn.create_group(active_txn_overrides={"sender": client}):
                    vault.release_payment(task_id, Address(treasury))

            # Status unchanged
            box_data = context.ledger.get_box(app_id, task_id.native.bytes)
            assert box_data[104] == 0

            # Case 2: status=SUBMITTED but kite_hash is zero — release should fail
            _submit_task_with_zero_hash(context, (vault, app_id, app_address), task_id)

            box_data = context.ledger.get_box(app_id, task_id.native.bytes)
            assert box_data[104] == 1  # SUBMITTED
            assert box_data[105:137] == b"\x00" * 32  # zero hash

            with pytest.raises(AssertionError):
                with context.txn.create_group(active_txn_overrides={"sender": client}):
                    vault.release_payment(task_id, Address(treasury))

            # Status unchanged
            box_data = context.ledger.get_box(app_id, task_id.native.bytes)
            assert box_data[104] == 1

    # Feature: semifinal-hardening, Property 4: Slash returns full bounty
    @given(bounty=st.integers(min_value=1, max_value=MAX_SAFE_BOUNTY))
    @settings(max_examples=200)
    @example(bounty=1)
    @example(bounty=49)
    @example(bounty=50)
    @example(bounty=51)
    @example(bounty=MAX_SAFE_BOUNTY)
    def test_slash_returns_full_bounty(self, bounty):
        """For any bounty in [1, 2^64-1], slash_bounty returns the full bounty
        to the client with no fee deducted (refund == bounty).

        **Validates: Requirements 2.5, 3.3**
        """
        # Feature: semifinal-hardening, Property 4: Slash returns full bounty
        with algopy_testing_context() as context:
            # Deploy
            vault = EscrowVault()
            vault.create(Address(context.default_sender))
            app_id = context.txn.last_group.txns[0].app_id
            app_address = Account(algosdk.logic.get_application_address(int(app_id.id)))

            # Accounts
            client = context.any.account()
            worker = context.any.account()
            sensei = context.any.account()

            # Lock bounty (status=LOCKED=0 — valid for slash)
            task_id_str = _unique_task_id()
            task_id = ARC4String(task_id_str)
            pay_txn = context.any.txn.payment(sender=client, receiver=app_address, amount=UInt64(bounty))
            deferred = context.txn.defer_app_call(
                vault.lock_bounty, task_id, Address(client), Address(worker),
                Address(sensei), ARC4UInt64(bounty), pay_txn
            )
            with context.txn.create_group([pay_txn, deferred]):
                deferred.submit()

            # Slash bounty
            with context.txn.create_group(active_txn_overrides={"sender": client}):
                vault.slash_bounty(task_id)

            # Extract inner transaction — single payment to client
            last_group = context.txn.last_group
            itxn_groups = last_group.itxn_groups
            assert len(itxn_groups) == 1, (
                f"Expected 1 inner txn group for slash, got {len(itxn_groups)}"
            )

            refund_itxn = itxn_groups[0][0]
            actual_refund = int(refund_itxn.amount)

            # Assert Property 4: full refund, no fee
            assert actual_refund == bounty, (
                f"Slash refund mismatch: got {actual_refund}, expected {bounty}"
            )
            assert refund_itxn.receiver == client, "Refund must go to client"
