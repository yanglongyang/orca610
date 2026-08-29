import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StateWorkflowTests(unittest.TestCase):
    def test_phase2_requires_human_selection_and_identity_before_emission(self):
        text = (ROOT / "scripts" / "phase2_s1.sh").read_text(encoding="utf-8")
        self.assertIn("require_state_selection", text)
        self.assertIn("require_state_identity", text)
        self.assertIn("followiroot ${FOLLOW_IROOT}", text)
        self.assertLess(text.index("require_state_selection"), text.index('opt_inp="${mol}_S1_Opt.inp"'))
        self.assertLess(text.index("require_state_identity"), text.index('em_inp="${mol}_S1_Emission.inp"'))
        self.assertNotIn("! Opt Freq", text)

    def test_esd_skips_without_the_optional_s1_frequency(self):
        text = (ROOT / "scripts" / "phase3_esd.sh").read_text(encoding="utf-8")
        self.assertIn('S1_FREQUENCY,,}" != "true"', text)
        self.assertIn("PHASE 3 SKIPPED", text)


if __name__ == "__main__":
    unittest.main()
