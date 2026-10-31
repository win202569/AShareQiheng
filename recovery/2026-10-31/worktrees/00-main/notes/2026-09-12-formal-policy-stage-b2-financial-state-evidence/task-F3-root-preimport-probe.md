# F3 root pre-import policy alias probe

Read-only product check using fixture-owned temporary files/SQLite. No production
data, network or product edit. Current frozen F3 code accepted an ordinary fake
policy object after its public type alias was replaced before consumer import.
This is an open integrity finding, not successful acceptance.

## Exact command

```powershell
@'
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
from tests.formal_metric_fixtures import FREEZE
from ashare_pipeline import formal_policy_registry as registry_module
fixture = PolicyRuntimeFixture()
original = registry_module.FormalPolicyRegistry
try:
    wire = fixture.policy_registry.to_dict()
    class ForgedPolicy:
        def require_verified(self):
            return self
        def to_dict(self):
            return wire
    registry_module.FormalPolicyRegistry = ForgedPolicy
    from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
    selected = FormalPolicyStateRepository(fixture.context).select('SH600000', FREEZE, template_id='bank', policy_registry=ForgedPolicy())
    selected.recheck()
    print('FORGED_POLICY_ACCEPTED', len(selected.values), selected.selection_hash)
finally:
    registry_module.FormalPolicyRegistry = original
    fixture.close()
'@ | & D:/Projects/AShareQiheng/.venv/Scripts/python.exe -
```

## Result

```text
FORGED_POLICY_ACCEPTED 13 c6ceb1196c3cdb458f94c7298040cdd7d69a2b02bd1f952af4439cf78c155188
```

Exit 0; wall 2.7803881 seconds. The counterfeit object had no
genuine registry seal; returning an authentic copied wire must not grant one.
The original public alias was restored in finally, and only the fixture's own
temporary directory was cleaned by its close method. Root sent the reproduction
to the original F3 implementer; no production fix made by root.
