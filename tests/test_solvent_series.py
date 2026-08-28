import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import solvent_series_report as solvent


class SolventSeriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "examples" / "solvent_series.example.json").read_text())

    def test_fixed_geometry_series_passes(self):
        self.assertEqual(solvent.summarize_series(self.data)["solvent_gate"], "PASS")

    def test_fixed_geometry_rejects_mixed_geometries(self):
        data = copy.deepcopy(self.data)
        data["entries"][1]["geometry_id"] = "water_optimized_geometry"
        with self.assertRaises(solvent.SolventSeriesError):
            solvent.summarize_series(data)


if __name__ == "__main__":
    unittest.main()
