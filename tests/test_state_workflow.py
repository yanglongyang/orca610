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

    def test_esd_uses_r0_selected_root_at_s0_geometry(self):
        text = (ROOT / "scripts" / "phase3_esd.sh").read_text(encoding="utf-8")
        self.assertIn('echo "  iroot ${selected_root}"', text)
        self.assertNotIn('echo "  iroot ${final_root}"', text)
        self.assertIn('echo "  cpcmeq ${IC_CPCMEQ}"', text)

    def test_s1_frequency_missing_summary_or_imaginary_mode_is_fatal(self):
        text = (ROOT / "scripts" / "phase2_s1.sh").read_text(encoding="utf-8")
        self.assertIn('S1 frequency summary missing; do not use this Hessian', text)
        self.assertIn('S1 frequency has $s1_imag imaginary modes; do not use this Hessian', text)


if __name__ == "__main__":
    unittest.main()
