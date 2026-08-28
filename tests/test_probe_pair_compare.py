import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import probe_pair_compare as pair


class ProbePairCompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "examples" / "probe_pair_results.example.json").read_text())

    def test_accepts_matched_probe_pair(self):
        result = pair.compare_pair(self.data)
        self.assertEqual(result["comparison_gate"], "PASS")
        self.assertAlmostEqual(result["deltas_comparison_minus_reference"]["E_abs_eV"], -0.25)

    def test_rejects_mixed_functional(self):
        data = copy.deepcopy(self.data)
        data["species_results"][1]["protocol"]["absorption"]["functional"] = "PBE0"
        with self.assertRaises(pair.ProbePairError):
            pair.compare_pair(data)

    def test_e00_requires_a_passing_energy_cycle_gate(self):
        data = copy.deepcopy(self.data)
        data["species_results"][1]["observables"]["E00"] = {"eV": 2.51}
        result = pair.compare_pair(data)
        self.assertIsNone(result["deltas_comparison_minus_reference"]["E00_eV"])
        self.assertEqual(result["validated_E00"]["comparison"]["status"], "NOT_VALIDATED")


if __name__ == "__main__":
    unittest.main()
