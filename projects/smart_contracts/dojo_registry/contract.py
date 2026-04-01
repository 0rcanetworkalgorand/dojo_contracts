from algopy import ARC4Contract, GlobalState, UInt64, Bytes, Txn, Account, op, urange
from algopy.arc4 import abimethod, Address, Bool, UInt64 as ARC4UInt64, String as ARC4String


class DojoRegistry(ARC4Contract):
    """Master agent identity store tracking lane assignment, status, config hash, task history, and expiry."""
    
    def __init__(self) -> None:
        self.admin = GlobalState(Account)
        self.total_agents = GlobalState(UInt64)
    
    @abimethod(create="require")
    def create(self, admin: Address) -> None:
        """Initialize the registry with admin address."""
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
        assert Txn.sender == self.admin.value, "Only admin can register"
        
        box_key = agent_id.native.bytes
        assert not op.Box.length(box_key), "Agent already registered"
        
        # Box format: sensei(32) + lane(8) + status(1) + config_hash(32) + tasks(8) + expiry(8)
        sensei_bytes = op.extract(sensei.native.bytes, 0, 32)
        lane_bytes = op.itob(lane.native)
        part1 = op.concat(sensei_bytes, lane_bytes)
        part2 = op.concat(op.bzero(1), config_hash)
        part3 = op.concat(part1, part2)
        box_data = op.concat(part3, op.bzero(16))
        op.Box.create(box_key, UInt64(89))
        op.Box.put(box_key, box_data)
        
        self.total_agents.value += UInt64(1)
        return Bool(True)
    
    @abimethod
    def update_status(self, agent_id: ARC4String, active: Bool) -> Bool:
        """Update agent operational status."""
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = agent_id.native.bytes
        length, exists = op.Box.length(box_key)
        assert exists, "Agent not found"
        
        data, _exists = op.Box.get(box_key)
        status_byte = Bytes(b"\x01") if active.native else Bytes(b"\x00")
        updated = data[:41] + status_byte + data[42:]
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod
    def increment_tasks(self, agent_id: ARC4String) -> Bool:
        """Increment cumulative task count."""
        assert Txn.sender == self.admin.value, "Only admin"
        
        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        task_count = op.btoi(op.extract(data, 74, 8))
        new_count = task_count + UInt64(1)
        updated = data[:74] + op.itob(new_count) + data[82:]
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod
    def set_expiry(self, agent_id: ARC4String, expiry_timestamp: ARC4UInt64) -> Bool:
        """Set listing expiry timestamp."""
        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)
        
        # Get sensei from box
        sensei = Account(op.extract(data, 0, 32))
        assert Txn.sender == sensei or Txn.sender == self.admin.value, "Only sensei or admin"
        
        updated = op.concat(data[:82], op.itob(expiry_timestamp.native))
        op.Box.put(box_key, updated)
        
        return Bool(True)
    
    @abimethod(readonly=True)
    def get_agent(self, agent_id: ARC4String) -> Bytes:
        """Retrieve full agent record."""
        box_key = agent_id.native.bytes
        data, _exists = op.Box.get(box_key)
        return data
