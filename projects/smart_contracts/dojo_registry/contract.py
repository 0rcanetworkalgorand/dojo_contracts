from algopy import ARC4Contract, GlobalState, UInt64, Bytes, Txn, Account, op, urange
from algopy.arc4 import (
    abimethod,
    Address,
    Bool,
    UInt64 as ARC4UInt64,
    String as ARC4String,
)


class DojoRegistry(ARC4Contract):
    """Master agent identity store tracking lane assignment, status, config hash, task history, and expiry."""

    def __init__(self) -> None:
        self.admin = GlobalState(Account)
        self.total_agents = GlobalState(UInt64)

    @abimethod(create="require")
    def create(self, admin: Address) -> None:
        """Initialize the registry with admin address."""
        # Hardcoded admin for now - will use parameter
        self.admin.value = admin.native
        self.total_agents.value = UInt64(0)

    @abimethod
    def register_agent(
        self,
        agent_id: ARC4String,
        sensei: Address,
        lane: ARC4UInt64,
        config_hash: Bytes,
    ) -> Bool:
        """Register a new agent with lane assignment and sealed config hash."""
        # Allow either admin or the sensei themselves to register
        assert Txn.sender == self.admin.value or Txn.sender == sensei.native, (
            "Unauthorized registration"
        )

        box_key = agent_id.native.bytes
        assert not op.Box.length(box_key)[1], "Agent already registered"

        # Box format: sensei(32) + lane(8) + status(1) + config_hash(32) + tasks(8) + failed_tasks(8) + expiry(8) = 97 bytes
        # status: 0=REGISTERED, 1=LISTED, 2=DELISTED
        sensei_bytes = op.extract(sensei.native.bytes, 0, 32)
        lane_bytes = op.itob(lane.native)
        part1 = op.concat(sensei_bytes, lane_bytes)
        part2 = op.concat(op.bzero(1), config_hash)  # Status (0) + config_hash
        part3 = op.concat(part1, part2)
        # tasks(8) + failed_tasks(8) + expiry(8) = 24 bytes
        box_data = op.concat(part3, op.bzero(24))
        op.Box.create(box_key, UInt64(97))
        op.Box.put(box_key, box_data)

        self.total_agents.value += UInt64(1)
        return Bool(True)

    @abimethod
    def list_agent(self, agent_id: ARC4String, expiry: ARC4UInt64) -> Bool:
        """List agent in marketplace with a specific expiry timestamp."""
        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)

        sensei = Account(op.extract(data, 0, 32))
        assert Txn.sender == sensei or Txn.sender == self.admin.value, (
            "Only sensei or admin"
        )

        # Update status to 1 (LISTED) and set expiry
        updated = data[:40] + Bytes(b"\x01") + data[41:89] + op.itob(expiry.native)
        op.Box.put(box_key, updated)
        return Bool(True)

    @abimethod
    def delist_agent(self, agent_id: ARC4String) -> Bool:
        """Remove agent from marketplace."""
        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)

        sensei = Account(op.extract(data, 0, 32))
        assert Txn.sender == sensei or Txn.sender == self.admin.value, (
            "Only sensei or admin"
        )

        # Update status to 2 (DELISTED)
        updated = data[:40] + Bytes(b"\x02") + data[41:]
        op.Box.put(box_key, updated)
        return Bool(True)

    @abimethod
    def increment_tasks(self, agent_id: ARC4String) -> Bool:
        """Increment cumulative successful task count."""
        assert Txn.sender == self.admin.value, "Only admin"

        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)

        task_count = op.btoi(
            op.extract(data, 73, 8)
        )  # Offset adjusted for new status byte and previous fields
        new_count = task_count + UInt64(1)
        updated = data[:73] + op.itob(new_count) + data[81:]
        op.Box.put(box_key, updated)

        return Bool(True)

    @abimethod
    def increment_tasks_failed(self, agent_id: ARC4String) -> Bool:
        """Increment cumulative failed task count (slashing)."""
        assert Txn.sender == self.admin.value, "Only admin"

        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)

        failed_count = op.btoi(op.extract(data, 81, 8))
        new_count = failed_count + UInt64(1)
        updated = data[:81] + op.itob(new_count) + data[89:]
        op.Box.put(box_key, updated)

        return Bool(True)

    @abimethod
    def update_status(self, agent_id: ARC4String, status: ARC4UInt64) -> Bool:
        """Update agent operational status manually."""
        assert Txn.sender == self.admin.value, "Only admin"

        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)

        status_byte = op.extract(op.itob(status.native), 7, 1)
        updated = data[:40] + status_byte + data[41:]
        op.Box.put(box_key, updated)

        return Bool(True)

    @abimethod(readonly=True)
    def get_agent(self, agent_id: ARC4String) -> Bytes:
        """Retrieve full agent record."""
        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)
        return data
