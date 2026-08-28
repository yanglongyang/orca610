import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RunOrcaGateTests(unittest.TestCase):
    def test_approval_precedes_existing_job_or_output_handling(self):
        text = (ROOT / "scripts" / "shared_functions.sh").read_text(encoding="utf-8")
        start = text.index("run_orca() {")
        end = text.index("#------------------------------------------------------------------------------\n# Data extraction", start)
        body = text[start:end]
        approval = body.index('require_input_approval "$input" "$outfile"')
        self.assertLess(approval, body.index('wait_for_job "$basename"'))
        self.assertLess(approval, body.index('if orca_done "$outfile"'))


if __name__ == "__main__":
    unittest.main()
