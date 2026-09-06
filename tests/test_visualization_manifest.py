import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import orbital_visualize as vis


OUT = """Program Version 6.1.0\nORBITAL ENERGIES\n NO OCC E(Eh) E(eV)\n 0 2.0000 -0.5 -13.6\n 1 2.0000 -0.1 -2.7\n 2 0.0000 0.05 1.3\nORCA TERMINATED NORMALLY\n"""


class VisualizationManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.work = Path(self.temp.name)
        (self.work / "job.out").write_text(OUT)
        (self.work / "job.gbw").write_bytes(b"gbw placeholder")
        (self.work / "job.xyz").write_text("3\ntriangle\nC 0 0 0\nC 1 0 0\nC 0 1 0\n")
        (self.work / "job.inp").write_text("# @FUNCTIONAL: CAM-B3LYP\n# @BASIS: def2-SVPD\n")

    def tearDown(self): self.temp.cleanup()

    def args(self, **override):
        data = dict(gbw=str(self.work / "job.gbw"), output=str(self.work / "job.out"), xyz=str(self.work / "job.xyz"), input=str(self.work / "job.inp"), orbitals="HOMO,LUMO", spin=None, all_spins=False, views="front,side", front_axis="smallest", side_axis="middle", isovalue=0.03, profile="publication", grid=100, directory=str(self.work / "visualization"), renderer="vmd", orca_plot=None, vmd=None, execute=False, comparison_manifest=None, allow_comparison_exception=False)
        data.update(override); return SimpleNamespace(**data)

    def test_plan_manifest_is_hashed_and_does_not_claim_rendering(self):
        manifest_path = vis.execute(self.args())
        data = json.loads(manifest_path.read_text())
        self.assertEqual(data["execution_mode"], "planned")
        self.assertEqual(data["source"]["orca_version"], "6.1.0")
        self.assertEqual(data["source"]["method_metadata"]["functional"], "CAM-B3LYP")
        self.assertEqual([entry["index"] for entry in data["orbitals"]], [1, 2])
        self.assertTrue(data["source"]["gbw"]["sha256"])
        self.assertTrue(all(item["status"] == "PLANNED" for item in data["render"]["results"]))
        self.assertTrue((manifest_path.parent / "render_HOMO_front.tcl").is_file())

    def test_comparison_mismatch_is_a_gate(self):
        baseline = vis.execute(self.args())
        with self.assertRaisesRegex(vis.VisualizationError, "COMPARISON_CONVENTION_MISMATCH"):
            vis.build_plan(self.args(isovalue=0.04, comparison_manifest=str(baseline)))
        plan = vis.build_plan(self.args(isovalue=0.04, comparison_manifest=str(baseline), allow_comparison_exception=True))
        self.assertTrue(plan["comparison"]["exception_approved"])


if __name__ == "__main__":
    unittest.main()
