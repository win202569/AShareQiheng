# Task 1 Fix Round 1 Review Package

工作区无 Git；以下 before/after SHA-256 界定本轮修复范围。审阅者只需读取 after 文件并针对原6项发现复核。

| 文件 | Before | After |
|---|---|---|
| `ashare_pipeline/state_store.py` | `0C28492A822EFB145C2FEA8670B75D19EA13B60A96974B0D7559DDB8A264776C` | `0651BDF5B2614FDA29DA473D7AF9382F3662FDD9A3C0EBC9F2D20D29802CDD4A` |
| `tests/test_state_store.py` | `0778A4838E3982DA263C100FD12AB1B782557181E4060E0A93AD7D26510AD512` | `B7A4E3C103B4EA94D08E0975C7F20AF3EE0285C44183236877682439ADFA320D` |
| `task-1-report.md` | `1480F166E43323333B35AFC844AF60E92FD0E70828CA43D2F25F329EEAA68B64` | `0025B3FEB44EDECB4653876E4A35BA53FA494937EDB2B117EE0EEF781C1B2B99` |

原发现：UTC持久化、upsert绕过final、final证据未持久化、progress更新时间遗漏、租约竞争测试不真实、跨偏移截止测试不足。

任务简报：`work/a_share_pipeline/task-1-brief.md`；实施报告：`work/a_share_pipeline/task-1-report.md`。
