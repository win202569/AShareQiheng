"""Read-only exact target-tree verification. Results are not live authority.

The configured recovery service must authenticate durable preparation records
before calling this function and fence its subsequent database transition.
"""
import hashlib
import os
from pathlib import Path
import stat
from .formal_release_types import ReleaseFile, canonical_preparation_bytes


def _identity(path, *, directory):
    value = path.lstat()
    if (stat.S_ISLNK(value.st_mode)
            or getattr(value, 'st_file_attributes', 0) & 0x400
            or (not stat.S_ISDIR(value.st_mode) if directory else not stat.S_ISREG(value.st_mode))
            or (not directory and value.st_nlink != 1)):
        raise ValueError('release tree contains a link, reparse point or invalid object')
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns, value.st_nlink,
            getattr(value, 'st_file_attributes', 0))


def _scan(root, files, directories):
    result = {'': _identity(root, directory=True)}
    pending = [root]
    seen = set()
    while pending:
        parent = pending.pop()
        with os.scandir(parent) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                folded = relative.casefold()
                if folded in seen:
                    raise ValueError('release tree contains case collisions')
                seen.add(folded)
                if relative in directories:
                    result[relative] = _identity(path, directory=True)
                    pending.append(path)
                elif relative in files:
                    result[relative] = _identity(path, directory=False)
                else:
                    raise ValueError('release tree contains an undeclared path: ' + relative)
    if set(result) != {''} | set(files) | directories:
        raise ValueError('release tree is missing declared files or directories')
    return result


def _verify_release_tree(path, preparation):
    """Verify a final target, returning detached descriptions with no write grant."""
    canonical_preparation_bytes(preparation)
    root = Path(path)
    if not root.is_absolute() or root.as_posix() != preparation.target_path:
        raise ValueError('release tree target differs from preparation')
    files = {item.path: (item.sha256, item.byte_size) for item in preparation.files}
    files['release_manifest.json'] = (preparation.manifest_sha256, preparation.manifest_byte_size)
    directories = {parent.as_posix() for name in files
                   for parent in Path(name).parents if parent != Path('.')}
    try:
        ancestors = {parent: _identity(parent, directory=True) for parent in root.parents}
        before = _scan(root, files, directories)
        for name, (expected_hash, expected_size) in files.items():
            target = root / name
            digest = hashlib.sha256()
            size = 0
            with target.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != before[name][:2]:
                    raise ValueError('release file changed while opening')
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > expected_size:
                        raise ValueError('release file exceeds prepared size')
                    digest.update(chunk)
            if size != expected_size or digest.hexdigest() != expected_hash:
                raise ValueError('release file differs from prepared bytes: ' + name)
            if _identity(target, directory=False) != before[name]:
                raise ValueError('release file changed during verification')
        if _scan(root, files, directories) != before:
            raise ValueError('release tree changed during verification')
        if any(_identity(parent, directory=True) != identity for parent, identity in ancestors.items()):
            raise ValueError('release tree ancestor changed during verification')
    except OSError as exc:
        raise ValueError('release tree cannot be read safely') from exc
    canonical_preparation_bytes(preparation)
    return tuple(ReleaseFile(item.path, item.sha256, item.byte_size) for item in preparation.files)


__all__ = []
