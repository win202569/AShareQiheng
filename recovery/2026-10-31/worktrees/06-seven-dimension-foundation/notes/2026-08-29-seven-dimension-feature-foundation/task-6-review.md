# Task 6 Final Independent Re-review

**APPROVED**

计数：Critical 0，Important 0，Minor 0。

## 并发 no-clobber finding 闭环

- ashare_pipeline/snapshot_store.py:48-59 不再覆盖 target。part 先在 target 同目录写完、fsync 并验签，再由 os.link(part, target) 执行原子 create-if-absent。两个同 digest、同日 writer 共享同一 target 时，只可能有一个 link 成功，符合 first-writer-wins。
- target 已存在时，Python 在 Windows 和 POSIX 都以 FileExistsError 进入 loser 分支；loser 单读验签现有 winner，仅 unlink 自己的唯一 part 名称并返回 winner。成功 publisher 也只 unlink 自己的 part 链接，target 名称及 inode 保留。生产路径没有 os.replace，也没有任何补偿删除 target。
- os.link 的 source 与 target 位于同一已验证目录和卷，规避跨卷硬链接错误。除 FileExistsError 外的权限、磁盘、文件系统等 OSError 不会被误判为 loser：外层失败关闭，只以 part_path.unlink(missing_ok=True) 清理本 writer 的 part 后重新抛出。Windows NTFS 上该真实系统调用已由报告中的 185/185 回归覆盖。
- tests/test_snapshot_repository.py:135-188 的受控双 writer 测试只在真实 os.link 外包 barrier，没有复制 no-clobber 逻辑。两者先越过 lookup；第一 writer 完成实际 link 和 DB 记录后第二 writer 才执行实际 link，因此真实覆盖 target-exists loser 分支。断言两个 persist 返回同一 SnapshotRef、created 标志分别为 true/false、ref 与最终文件均使用 first winner 时间，且两次 read_verified 均成功。
- tests/test_snapshot_store.py 的 no-clobber 失败测试令 os.link 抛普通 OSError，并确认 part 与 target 均不残留，覆盖非 FileExistsError 的 own-part cleanup 分支。

## Repository 使用实际 winner 元数据

- ashare_pipeline/snapshot_repository.py:48-72 在 SnapshotStore.write() 返回后重新单读并验签实际 target，不使用当前调用 batch 的 fetched_at 直接入库。
- winner.canonical_bytes() 必须与请求 batch 的 canonical content identity 相同，request fingerprint 也必须一致；fetch time 按设计不属于内容身份，因此不同观察时间仍可安全复用 first winner。
- StateStore.record_snapshot() 使用 winner.source、winner.dataset、winner request fingerprint、winner row count 和规范 UTC winner.fetched_at_utc。并发 loser 不会把自己的时间写到唯一 DB 行，read_verified 的 DB/payload 双向时间核对保持成立。
- 同日期 loser 返回共同 target；跨日期并发若各自发布同 digest，唯一 DB 约束仍让两次 persist 返回同一已登记 ref，额外文件只是 data_root 内、已验签且不被竞态删除的文档化 orphan。

## 原审查项与整体范围

- fetched_at 双向规范 UTC 比对、store 单读同对象验签返回、source/dataset 写前安全组件校验、注入 root 一致性、relative backslash 拒绝均保持闭环。
- canonical request exact scoping、revision tie-break、SnapshotRef DB 映射、get exact ID、source/version/metadata hash 提交、row_count、legacy absolute 与新 relative containment 未被并发修复削弱。
- verified-orphan 策略只留存 data_root 内的已验签内容，不进行可能删除另一 writer target 的补偿操作；不存在 data_root 外写或竞态删除回归。
- 累计提交仍只修改 snapshot_repository.py、snapshot_store.py 及其两份测试，符合 Task 6 范围。

## 验证边界

- 完整阅读更新 task-6-report.md、review-95d2f56..57decb7.diff，并对照当前两个生产文件和并发测试。
- 按要求信任报告中的 snapshot suite 27 项、完整 185/185、py_compile 与 diff-check，未重跑测试或新增探针。
- 未访问仓库 data/；除覆盖本审查文件外未修改实现、测试或提交。
