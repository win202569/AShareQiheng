"""Complete final-tree checks are data verification, never publication authority."""
from contextlib import closing
from dataclasses import replace
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from ashare_pipeline.formal_release_types import ReleaseFile, ReleasePreparationPayload


class ReleaseTreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ('20260831-formal-v3-'+'a'*64)
        self.root.mkdir()
        self.contents = {'scores.csv':b'id,score\nSH600000,90\n', 'audit_cards/SH600000.json':b'{}'}
        for name, raw in self.contents.items():
            path=self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (self.root/'release_manifest.json').write_bytes(b'{}')
        self.preparation = ReleasePreparationPayload('a'*64,'run','b'*64,'c'*64,'d'*64,
            hashlib.sha256(b'{}').hexdigest(),2,'v1',self.root.as_posix(),
            tuple(ReleaseFile(name,hashlib.sha256(raw).hexdigest(),len(raw)) for name,raw in sorted(self.contents.items())), '{}')

    def verify(self, root=None, preparation=None):
        spec=importlib.util.find_spec('ashare_pipeline.formal_release_tree')
        self.assertIsNotNone(spec, 'release tree verifier is missing')
        from ashare_pipeline.formal_release_tree import _verify_release_tree
        return _verify_release_tree(self.root if root is None else root, self.preparation if preparation is None else preparation)

    def test_complete_tree_returns_only_detached_file_descriptions(self):
        result=self.verify()
        self.assertEqual(result, self.preparation.files)
        self.assertIsInstance(result, tuple)
        self.assertFalse(hasattr(result,'publish'))

    def test_changed_or_missing_payload_is_rejected(self):
        path=self.root/'scores.csv'
        path.write_bytes(b'bad')
        with self.assertRaises(ValueError): self.verify()
        path.unlink()
        with self.assertRaises(ValueError): self.verify()

    def test_extra_files_and_empty_directories_are_rejected(self):
        path=self.root/'extra'
        path.write_bytes(b'x')
        with self.assertRaises(ValueError): self.verify()
        path.unlink(); path.mkdir()
        with self.assertRaises(ValueError): self.verify()

    def test_manifest_bytes_must_match_preparation(self):
        (self.root/'release_manifest.json').write_bytes(b'{ }')
        with self.assertRaises(ValueError): self.verify()

    def test_wrong_target_and_tampered_preparation_are_rejected(self):
        with self.assertRaises(ValueError): self.verify(root=self.root.parent)
        object.__setattr__(self.preparation.files[0],'path','../escape')
        with self.assertRaises(ValueError): self.verify()

    def test_hardlinked_payload_is_rejected(self):
        outside=Path(self.temp.name)/'outside.csv'
        outside.write_bytes(self.contents['scores.csv'])
        (self.root/'scores.csv').unlink()
        os.link(outside, self.root/'scores.csv')
        with self.assertRaises(ValueError): self.verify()

    def test_file_in_place_of_required_directory_is_rejected(self):
        (self.root/'audit_cards/SH600000.json').unlink()
        (self.root/'audit_cards').rmdir()
        (self.root/'audit_cards').write_bytes(b'x')
        with self.assertRaises(ValueError): self.verify()

    def test_windows_reparse_attribute_is_rejected(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        original=Path.lstat
        target=self.root/'scores.csv'
        def marked(path,*args,**kwargs):
            value=original(path,*args,**kwargs)
            if path==target:
                return SimpleNamespace(st_mode=value.st_mode,st_file_attributes=0x400)
            return value
        with patch.object(Path,'lstat',marked):
            with self.assertRaisesRegex(ValueError,'reparse|link'): self.verify()

    def test_case_alias_is_rejected(self):
        path=self.root/'scores.csv'
        path.rename(self.root/'temporary.csv')
        (self.root/'temporary.csv').rename(self.root/'SCORES.csv')
        with self.assertRaises(ValueError): self.verify()
