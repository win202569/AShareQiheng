# Wave 1 joint verification

Command: `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_policy_values -q`

Session 85820, exit 0:

```text
Ran 34 tests in 99.500s
OK
```

All nine implementation/test files matched their pre-run SHA-256 at completion.
This run covers R1/F1 together after fix round 1; it does not claim all Stage B is
implemented or replace each worker's prescribed legacy compatibility evidence.

| File | SHA-256 |
| --- | --- |
| ashare_pipeline/formal_range_format.py | C6F3504F5B65BDBAAF3ED21D8C7D4F3CAE58748EA5F449FA2CFCC6B442A2E517 |
| ashare_pipeline/formal_range_contract.py | 5F646ACA4332E6A9287E3E7E7FE99DBC7A0487A14D405580776A267FB2898746 |
| ashare_pipeline/formal_sources.py | D854AA889EB3143F44F3FBB855DD7F00FB5F078B535F59F83F82B0E6FA6309F4 |
| ashare_pipeline/formal_policy_values.py | 9D8679B9F343E9C18A821204C237DF89D3D4D74D84A7EAA93A47EBA905D14772 |
| tests/formal_metric_feature_fixtures.py | A1CC4E64803A366033B35EEA96A2D6805BADF1C7236EA52C7BE171293BAD6007 |
| tests/formal_policy_runtime_fixtures.py | 4DA500AD875E74396CABD33820687ACBEA199225262742F59B32FE7D3F7133C9 |
| tests/formal_range_fixtures.py | 12CE3232BEF49B6CC59B9EE849692199E205BAD4E5F920E3B533A82BB4B80E5B |
| tests/test_formal_policy_values.py | B80279F91AA7DA17B0C565107A9F1058958D18228BDAD9CC89A7C704E35A214B |
| tests/test_formal_range_contract.py | 72925F06DD0B4C3AA6F4920D01D53F59E80FA5695BE63387D02D4ED5E1401EFB |

