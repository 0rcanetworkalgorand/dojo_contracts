import pytest
from algopy_testing import AlgopyTestContext, algopy_testing_context
from algopy import Account, Bytes, UInt64, op
from algopy.arc4 import Address, UInt64 as ARC4UInt64, String as ARC4String, Bool

from projects.smart_contracts.dojo_registry.contract import DojoRegistry


@pytest.fixture()
def context():
    with algopy_testing_context() as ctx:
        yield ctx


@pytest.fixture()
def deployed(context: AlgopyTestContext):
    """Deploy DojoRegistry and return (contract, app_id)."""
    registry = DojoRegistry()
    registry.create(Address(context.default_sender))
    app_id = context.txn.last_group.txns[0].app_id
    return registry, app_id


@pytest.fixture()
def sensei(context: AlgopyTestContext):
    return context.any.account()


def _register(context, deployed, sensei, agent_id_str="research-abc123", lane=0):
    """Helper: register an agent and return the agent_id."""
    registry, app_id = deployed
    agent_id = ARC4String(agent_id_str)
    lane_val = ARC4UInt64(lane)
    config_hash = Bytes(b"\xaa" * 32)

    with context.txn.create_group(active_txn_overrides={"sender": context.default_sender}):
        registry.register_agent(agent_id, Address(sensei), lane_val, config_hash)
    return agent_id


class TestCreate:
    def test_create_sets_admin(self, context: AlgopyTestContext, deployed):
        registry, _ = deployed
        assert registry.admin.value == context.default_sender
        assert registry.total_agents.value == UInt64(0)


class TestRegisterAgent:
    def test_register_by_admin(self, context: AlgopyTestContext, deployed, sensei):
        """Admin registers an agent — 97-byte box created."""
        registry, app_id = deployed
        agent_id = _register(context, deployed, sensei)

        assert registry.total_agents.value == UInt64(1)
        box_data = context.ledger.get_box(app_id, agent_id.native.bytes)
        assert len(box_data) == 97
        # Status at offset 40 is 0 (REGISTERED)
        assert box_data[40] == 0

    def test_register_by_sensei(self, context: AlgopyTestContext, deployed, sensei):
        """Sensei can self-register their own agent."""
        registry, app_id = deployed
        agent_id = ARC4String("code-self01")
        lane = ARC4UInt64(1)
        config_hash = Bytes(b"\xbb" * 32)

        with context.txn.create_group(active_txn_overrides={"sender": sensei}):
            result = registry.register_agent(agent_id, Address(sensei), lane, config_hash)

        assert result == Bool(True)

    def test_register_unauthorized_fails(self, context: AlgopyTestContext, deployed, sensei):
        """Random user cannot register for another sensei."""
        registry, _ = deployed
        random_user = context.any.account()
        agent_id = ARC4String("data-bad001")
        lane = ARC4UInt64(2)
        config_hash = Bytes(b"\xcc" * 32)

        with pytest.raises(AssertionError, match="Unauthorized registration"):
            with context.txn.create_group(active_txn_overrides={"sender": random_user}):
                registry.register_agent(agent_id, Address(sensei), lane, config_hash)

    def test_register_duplicate_fails(self, context: AlgopyTestContext, deployed, sensei):
        """Cannot register the same agent_id twice."""
        registry, _ = deployed
        _register(context, deployed, sensei, agent_id_str="outreach-dup01", lane=3)

        agent_id = ARC4String("outreach-dup01")
        lane = ARC4UInt64(3)
        config_hash = Bytes(b"\xdd" * 32)

        with pytest.raises(AssertionError, match="Agent already registered"):
            with context.txn.create_group(active_txn_overrides={"sender": context.default_sender}):
                registry.register_agent(agent_id, Address(sensei), lane, config_hash)


class TestIncrementTasks:
    def test_increment_tasks_success(self, context: AlgopyTestContext, deployed, sensei):
        """Admin increments successful task count."""
        registry, app_id = deployed
        agent_id = _register(context, deployed, sensei, "agent-inc")
        admin = context.default_sender

        with context.txn.create_group(active_txn_overrides={"sender": admin}):
            result = registry.increment_tasks(agent_id)

        assert result == Bool(True)
        box_data = context.ledger.get_box(app_id, agent_id.native.bytes)
        tasks_count = int.from_bytes(box_data[73:81], "big")
        assert tasks_count == 1

    def test_increment_failed_success(self, context: AlgopyTestContext, deployed, sensei):
        """Admin increments failed task count."""
        registry, app_id = deployed
        agent_id = _register(context, deployed, sensei, "agent-fail")
        admin = context.default_sender

        with context.txn.create_group(active_txn_overrides={"sender": admin}):
            result = registry.increment_tasks_failed(agent_id)

        assert result == Bool(True)
        box_data = context.ledger.get_box(app_id, agent_id.native.bytes)
        failed_count = int.from_bytes(box_data[81:89], "big")
        assert failed_count == 1

    def test_increment_non_admin_fails(self, context: AlgopyTestContext, deployed, sensei):
        """Non-admin cannot increment counters."""
        registry, _ = deployed
        agent_id = _register(context, deployed, sensei, "agent-unauth")

        with pytest.raises(AssertionError, match="Only admin"):
            with context.txn.create_group(active_txn_overrides={"sender": sensei}):
                registry.increment_tasks(agent_id)
