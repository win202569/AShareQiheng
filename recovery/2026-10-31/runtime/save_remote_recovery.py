"""Create a checked recovery tree without changing any live checkout/index."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

MAIN = Path(r'D:\Projects\AShareQiheng')
CODE = Path(r'C:\Users\Lenovo\.codex\worktrees\formal-final-stage-d\AShareQiheng')
BASE = '756fdfc38c27df4a9ea5ee01f15117ce7e9f3b00'
BRANCH = 'codex/recovery-2026-10-31'
STAGE = MAIN / '.tmp' / 'remote-recovery-20261031'
REL = Path('recovery/2026-10-31')
ROOT = STAGE / REL

def git(*args, cwd=CODE, env=None):
    return subprocess.check_output(['git', *args], cwd=cwd, env=env)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

def database(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)
            result = dst.execute('PRAGMA integrity_check').fetchall()
            if result != [('ok',)]:
                raise ValueError(f'database integrity failure: {source}')

def main():
    if git('rev-parse', 'HEAD').decode().strip() != BASE:
        raise ValueError('live checkpoint changed')
    if STAGE.exists():
        raise ValueError('snapshot directory already exists; refusing overwrite')
    ROOT.mkdir(parents=True)
    items = git('worktree', 'list', '--porcelain', cwd=MAIN).decode().splitlines()
    paths = [Path(line[9:]) for line in items if line.startswith('worktree ')]
    inventory = []
    for index, path in enumerate(paths):
        label = f'{index:02d}-' + ('main' if path == MAIN else path.parent.name if path == CODE else path.name)
        dest = ROOT / 'worktrees' / label
        dest.mkdir(parents=True)
        status = git('status', '--porcelain=v1', '-z', cwd=path)
        (dest / 'working-tree.patch').write_bytes(git('diff', '--binary', 'HEAD', cwd=path))
        # Preserve ignored project-progress notes, not credentials or runtime DBs.
        notes = path / '.superpowers' / 'sdd'
        if notes.exists():
            for source in notes.rglob('*'):
                if source.is_file() and (source.suffix in ('.md', '.diff') or source.name in ('plan-path', '.gitignore')):
                    copy_file(source, dest / 'notes' / source.relative_to(notes))
        inventory.append(dict(path=str(path), label=label,
            branch=git('branch', '--show-current', cwd=path).decode().strip(),
            head=git('rev-parse', 'HEAD', cwd=path).decode().strip(),
            status=status.decode(errors='replace').split('\0')))
    # Both active datasets are captured; SQLite backup includes committed WAL state.
    for label, path in (('main', MAIN), ('formal-final-stage-d', CODE)):
        for source in (path / 'data').rglob('*'):
            if not source.is_file() or source.name.endswith(('-wal', '-shm')):
                continue
            target = ROOT / 'data-snapshots' / label / source.relative_to(path)
            if source.suffix in ('.sqlite', '.sqlite3', '.db'):
                database(source, target)
            else:
                copy_file(source, target)
    legacy = MAIN / '恢复进度文档-另一台电脑.md'
    if legacy.exists():
        copy_file(legacy, ROOT / 'historical-recovery-instructions.md')
    runtime = MAIN / '.tmp'
    names = ['grouped_regression.py', 'test_grouped_regression.py',
             'independent_verification.ps1', 'test_independent_task.py',
             'v9-release-progress.md', 'interruption-diagnosis-2026-10-16.md',
             'save_remote_recovery.py']
    for name in names:
        copy_file(runtime / name, ROOT / 'runtime' / name)
    for folder in sorted(runtime.glob('grouped-checkpoint-*')):
        journal = folder / 'journal.jsonl'
        if journal.exists():
            raw = journal.read_bytes()
            raw = raw[:raw.rfind(b'\n') + 1]
            dest = ROOT / 'runtime' / folder.name
            dest.mkdir(parents=True)
            (dest / journal.name).write_bytes(raw)
            for source in folder.iterdir():
                if source.is_file() and source.suffix in ('.json', '.log'):
                    copy_file(source, dest / source.name)
    for folder in sorted(runtime.glob('independent-*')):
        if folder.is_dir():
            for source in folder.iterdir():
                if source.is_file() and source.suffix in ('.json', '.log'):
                    copy_file(source, ROOT / 'runtime' / folder.name / source.name)
    # Validate every completed group against its copied log, no new authority.
    validated = {}
    for journal in (ROOT / 'runtime').glob('grouped-*/journal.jsonl'):
        counts = dict(passed_groups=0, nonzero_groups=0)
        for line in journal.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row.get('event') == 'finish':
                log = journal.parent / Path(row['log']).name
                if sha(log) != row['log_hash']:
                    raise ValueError(f'copied completed log hash mismatch: {log}')
                counts['passed_groups' if row['exit_code'] == 0 else 'nonzero_groups'] += 1
        validated[journal.parent.name] = counts
    import importlib.metadata
    import sys
    environment = dict(python=sys.version, executable=sys.executable,
        packages=sorted((dict(name=d.metadata['Name'], version=d.version)
                         for d in importlib.metadata.distributions()), key=lambda d: d['name'].lower()))
    (ROOT / 'python-environment.json').write_text(json.dumps(environment, indent=2), encoding='utf-8')
    copy_file(runtime / 'RECOVER-2026-10-31.md', ROOT / 'README.md')
    metadata = dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),
        source_checkpoint=BASE, recovery_branch=BRANCH, worktrees=inventory,
        journals=validated, databases='SQLite online backup; integrity_check=ok',
        verification_observation=dict(state='interrupted; not running at 2026-10-31 inspection',
            scheduler_result=1073807364, last_heartbeat='2026-10-19T13:16:26.337045+00:00',
            full_suite_passed=False, interruption_cause='not established'),
        exclusions=['credentials/env files', 'virtualenv/cache', 'obsolete nested Git mirrors/bundles',
                    'disposable synthetic test databases', 'OS task registrations and locks'])
    (ROOT / 'snapshot.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {p.relative_to(ROOT).as_posix(): dict(bytes=p.stat().st_size, sha256=sha(p))
                for p in sorted(ROOT.rglob('*')) if p.is_file()}
    (ROOT / 'sha256-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(dict(stage=str(STAGE), files=len(manifest),
        bytes=sum(v['bytes'] for v in manifest.values()), journals=validated)))

if __name__ == '__main__':
    main()
