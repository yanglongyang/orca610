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
        self.assertLess(body.index('require_experience_check "$input"'), approval)
        self.assertLess(approval, body.index('wait_for_job "$basename"'))
        self.assertLess(approval, body.index('if orca_done "$outfile"'))
        self.assertLess(body.index('require_orca_version_match "$input"'), body.index('wait_for_job "$basename"'))

    def test_actual_orca_version_is_parsed_from_output_and_recorded(self):
        text = (ROOT / "scripts" / "shared_functions.sh").read_text(encoding="utf-8")
        self.assertIn("get_orca_output_version()", text)
        self.assertIn("[PROVENANCE-GATE] ORCA VERSION MISMATCH", text)
        self.assertIn('record_actual_orca_version "$input" "$outfile"', text)
        self.assertIn('record_actual_orca_version "${basename}.inp" "$outfile"', text)
        self.assertIn('"input_sha256": __import__("hashlib").sha256(input_path.read_bytes()).hexdigest()', text)


if __name__ == "__main__":
    unittest.main()
