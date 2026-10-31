"""Real process tests for the one-shot wrapper's exit/result contract."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('independent_verification.ps1')

class IndependentTaskTests(unittest.TestCase):
    def run_case(self, mode, expected):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([
                'powershell.exe', '-NoProfile', '-NonInteractive', '-File',
                str(SCRIPT), '-Mode', mode, '-RunDirectory', folder,
                '-SmokeSeconds', '1'], capture_output=True, text=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            status = json.loads((Path(folder) / 'status.json').read_text(encoding='utf-8-sig'))
            self.assertEqual(status['phase'], 'finished')
            self.assertEqual(status['exit_code'], expected)
            self.assertIn('PROBE_FINISHED', (Path(folder) / 'output.log').read_text(encoding='utf-8-sig'))

    def test_success_records_real_child_completion(self):
        self.run_case('smoke', 0)

    def test_child_failure_is_not_reported_as_success(self):
        self.run_case('failure', 7)

if __name__ == '__main__':
    unittest.main(verbosity=2)
