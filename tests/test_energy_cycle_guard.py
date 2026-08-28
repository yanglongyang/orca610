import copy
import json
import sys
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
import energy_cycle_guard as guard


class EnergyCycleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads(
            (REPOSITORY / "examples" / "energy_cycle.example.json").read_text()
        )

    def test_accepts_state_appropriate_dft_and_tddft_families(self):
        self.assertEqual(guard.method_diff(self.example["energies"]), [])

    def test_rejects_mixed_ground_state_method_family(self):
        data = copy.deepcopy(self.example)
        data["energies"]["E0_R1"]["method"]["method_family"] = "HF"
        self.assertTrue(
            any("ground-state method_family" in issue for issue in guard.method_diff(data["energies"]))
        )

    def test_rejects_mixed_excited_state_response_settings(self):
        data = copy.deepcopy(self.example)
        data["energies"]["E1_R1"]["method"]["tda"] = True
        self.assertTrue(
            any("excited-state tda" in issue for issue in guard.method_diff(data["energies"]))
        )

    def test_rejects_missing_shared_provenance(self):
        data = copy.deepcopy(self.example)
        for point in data["energies"].values():
            del point["method"]["basis"]
        self.assertTrue(
            any("lacks shared fingerprint field 'basis'" in issue for issue in guard.method_diff(data["energies"]))
        )


if __name__ == "__main__":
    unittest.main()
