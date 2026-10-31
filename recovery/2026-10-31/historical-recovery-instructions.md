# 从另一台电脑恢复项目进度（AShareQiheng）

本项目目前在主机上已创建了三条可恢复备份分支，可供换机继续开发：

- `backup/20260906/main-progress` → `5a52010`
- `backup/20260906/report-date-repair` → `7fb4df3`
- `backup/20260906/seven-dimension-foundation` → `3e78967`

下面按“有网恢复”和“离线恢复”两种场景给出标准流程。

## 方案 A：有网恢复（推荐）

1. 在新电脑先配置 SSH/HTTPS 能访问 GitHub

```powershell
git remote -v
```

2. 克隆主仓库

```powershell
git clone https://github.com/win202569/AShareQiheng.git D:\Projects\AShareQiheng
cd D:\Projects\AShareQiheng
```

如果看到 “detected dubious ownership” 报错（仓库属主与当前用户不一致），先执行：

```powershell
git config --global --add safe.directory D:/Projects/AShareQiheng
```

3. 拉取所有远端分支

```powershell
git fetch --all --prune
```

4. 检查备份分支是否到位

```powershell
git ls-remote --heads origin backup/20260906/main-progress backup/20260906/report-date-repair backup/20260906/seven-dimension-foundation
```

预期返回三条 refs（SHA 不变）。

5. 在本机恢复到备份工作区（任选其一）

```powershell
git checkout -b restore/main-progress origin/backup/20260906/main-progress
```

或恢复其他两条：

```powershell
git checkout -b restore/report-date-repair origin/backup/20260906/report-date-repair
git checkout -b restore/seven-dimension-foundation origin/backup/20260906/seven-dimension-foundation
```

6. 建议先校验关键文件是否存在（示例）

```powershell
git status --short
ls .superpowers/sdd
Get-ChildItem data | Select-Object -ExpandProperty Name
```

7. 如需把备份内容并入当前开发分支（例如 main / feature），可在确认后用 cherry-pick 或 merge：

```powershell
git checkout main
git cherry-pick 5a52010
```

> 建议谨慎操作：`main-progress` 分支里包含的是快照，不一定适合直接覆盖主线。

---

## 方案 B：离线恢复（有 `.bundle` 或裸仓）

如果没有网络但有以下任一离线介质，可直接恢复：

- `AShareQiheng-backup-20260906.bundle`
- `AShareQiheng-backup-20260906.git`（裸仓）

### B1. 使用 `.bundle`

```powershell
git clone D:\Projects\AShareQiheng\AShareQiheng-backup-20260906.bundle D:\Projects\AShareQiheng_recover
cd D:\Projects\AShareQiheng_recover
git branch -a
git checkout -b restore/main-progress refs/heads/backup/20260906/main-progress
```

### B2. 使用裸仓

```powershell
git clone D:\Projects\AShareQiheng\AShareQiheng-backup-20260906.git D:\Projects\AShareQiheng_recover
cd D:\Projects\AShareQiheng_recover
git remote -v
git fetch
git checkout -b restore/main-progress origin/backup/20260906/main-progress
```

---

## 恢复后建议操作清单（防止继续卡住）

1. 先只读核查，不立即提交代码
2. 运行 `git status`，确认与预期未意外改动
3. 若继续开发，继续在 `restore/...` 分支中工作
4. 提交前同步到远端新分支，不再复用历史备份分支

---

## 说明

- `tmp_push_mirror_20260906`、本地裸仓仅用于备份传输中间态；不需要可不带到新机。
- 为避免 `.tmp-*`、`state.sqlite3-shm/wal` 在不同环境差异下波动，建议恢复后优先以 `git status` 与文件清单核对。
- 如果你希望，我可以再补一版“一键恢复脚本”（PowerShell），支持输入仓库路径后自动恢复三条备份分支。
