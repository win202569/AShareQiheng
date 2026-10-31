# F3 root pre-import value alias probe

Product source remained unmodified. A synthetic runtime fixture had no state
factors, but replacing the public PolicyValue alias before first state import
turned twelve missing booleans into present true values; recheck also accepted.

```powershell
@'
import copy
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
from tests.formal_metric_fixtures import FREEZE
from ashare_pipeline import formal_policy_values as value_module
fixture = PolicyRuntimeFixture()
original = value_module.PolicyValue
try:
    class ForgedValue:
        @classmethod
        def from_dict(cls, wire):
            wire = copy.deepcopy(wire)
            if wire['value_type'] == 'bool':
                wire.update(state='value', value=True, pending=[])
            return original.from_dict(wire)
        def to_dict(self):
            raise AssertionError('not used')
    value_module.PolicyValue = ForgedValue
    from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
    selected = FormalPolicyStateRepository(fixture.context).select('SH600000', FREEZE, template_id='bank', policy_registry=fixture.policy_registry)
    selected.recheck()
    present = [value for value in selected.values.values() if value.value_type == 'bool' and value.state == 'value']
    print('FORGED_VALUES_ACCEPTED', len(present), all(value.value is True for value in present))
finally:
    value_module.PolicyValue = original
    fixture.close()
'@ | & D:/Projects/AShareQiheng/.venv/Scripts/python.exe -
```

```text
FORGED_VALUES_ACCEPTED 12 True
```

Session 84709 completed with exit 0. No complete wall duration is claimed because
the process yielded across several polling calls. The original alias was restored
and only the fixture-owned temporary directory cleaned in finally. This is an
open integrity finding, not a legitimate policy result. Implementer notified;
original owner parser/serializer anchors required before consumer import.
