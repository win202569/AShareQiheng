# Review package — Task 11 temporary-root hang fix

Base: `b618191115b79a282de42cc6c27b124384cc5196`

Head: `d8540a613ea33736f333270a0b78e196739403ac`

Commit: `d8540a6 test: use writable formal feature temp root`

Tracked files changed: exactly `tests/test_formal_feature_store.py`

Stat: 17 insertions, 1 deletion.

```diff
diff --git a/tests/test_formal_feature_store.py b/tests/test_formal_feature_store.py
index 219cc1f..472ac7f 100644
--- a/tests/test_formal_feature_store.py
+++ b/tests/test_formal_feature_store.py
@@ -23,7 +23,9 @@ from ashare_pipeline.formal_feature_store import (
 
 
 PROJECT_TEST_TEMP_ROOT = (
-    Path(__file__).resolve().parents[1] / ".tmp" / "formal-feature-store-tests"
+    Path(tempfile.gettempdir()).resolve()
+    / "AShareQiheng"
+    / "formal-feature-store-tests"
 )
 
 
@@ -92,6 +94,19 @@ def create_directory_link(link: Path, target: Path) -> None:
         os.symlink(target, link, target_is_directory=True)
 
 
+class ProjectTemporaryDirectoryTests(unittest.TestCase):
+    def test_helper_uses_writable_user_temp_root(self) -> None:
+        declared_temp_root = Path(tempfile.gettempdir()).resolve()
+        self.assertTrue(PROJECT_TEST_TEMP_ROOT.resolve().is_relative_to(declared_temp_root))
+
+        with project_temporary_directory() as directory:
+            probe = Path(directory) / "write-probe.txt"
+            probe.write_text("temporary root is writable", encoding="utf-8")
+            self.assertEqual(probe.read_text(encoding="utf-8"), "temporary root is writable")
+            probe.unlink()
+            self.assertEqual(Path(directory).parent.resolve(), PROJECT_TEST_TEMP_ROOT.resolve())
+
+
 class FormalFeatureStoreTests(unittest.TestCase):
     def setUp(self) -> None:
         self.tempdir = project_temporary_directory()
```

Verification evidence:

- RED: isolated new test failed immediately because the old checkout-local
  stable root was not below `tempfile.gettempdir()`; helper was not called.
- Focused GREEN: 1/1.
- Fixture smoke: `FinalScoringFixture(peer_count=3, purpose="test")`
  constructed and closed inside a 30-second external bound.
- Default managed `C:\Users\Lenovo\AppData\Local\Temp` run exposed a second,
  separate sandbox restriction: `_SecureDirectory` cannot acquire GENERIC_READ
  handles on an ancestor in `C:\Users\Lenovo`; 18 tests reported 6 failures
  and 13 errors.
- With only child-process `TEMP` and `TMP` set to the authorized writable root
  `D:\Projects\AShareQiheng\.tmp`, the complete module passed 18/18 in 0.331s
  with one platform symlink skip. No production/test code changed between the
  two runs. A direct real `_SecureDirectory` smoke under that D: root also
  printed `SECURE_OK`.
- `git diff --check` and AST parse passed.
- No D1/full Task 11 suite was run after this commit.

The intended suite7 launch environment is `TEMP/TMP` under the authorized
writable D: project `.tmp`; this is runner environment configuration, not a
hard-coded production or test path.
