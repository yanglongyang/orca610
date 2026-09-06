import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
        data = dict(gbw=str(self.work / "job.gbw"), output=str(self.work / "job.out"), xyz=str(self.work / "job.xyz"), input=str(self.work / "job.inp"), orbitals="HOMO,LUMO", spin=None, all_spins=False, views="front,side", front_axis="smallest", side_axis="middle", isovalue=0.03, profile="publication", grid=100, directory=str(self.work / "visualization"), renderer="vmd", orca_plot=None, vmd=None, orca_plot_timeout=600, vmd_timeout=600, execute=False, comparison_manifest=None, allow_comparison_exception=False, comparison_exception_reason=None)
        data.update(override); return SimpleNamespace(**data)

    def test_plan_manifest_is_hashed_and_does_not_claim_rendering(self):
        manifest_path = vis.execute(self.args())
        data = json.loads(manifest_path.read_text())
        self.assertEqual(data["execution_mode"], "planned")
        self.assertEqual(data["overall_status"], "PLANNED")
        self.assertEqual(data["source"]["orca_version"], "6.1.0")
        self.assertEqual(data["source"]["method_metadata"]["functional"], "CAM-B3LYP")
        self.assertEqual([entry["index"] for entry in data["orbitals"]], [1, 2])
        self.assertTrue(data["source"]["gbw"]["sha256"])
        self.assertTrue(all(item["status"] == "PLANNED" for item in data["render"]["results"]))
        self.assertTrue((manifest_path.parent / "render_HOMO_front.tcl").is_file())
        self.assertEqual(data["source_binding"]["out_gbw"], "VERIFIED")
        self.assertEqual(data["render"]["view_axis_selectors"], {"front": "smallest", "side": "middle"})
        self.assertIn("{{{", (manifest_path.parent / "render_HOMO_front.tcl").read_text())

    def test_comparison_mismatch_is_a_gate(self):
        baseline = vis.execute(self.args())
        with self.assertRaisesRegex(vis.VisualizationError, "COMPARISON_CONVENTION_MISMATCH"):
            vis.build_plan(self.args(isovalue=0.04, comparison_manifest=str(baseline)))
        with self.assertRaisesRegex(vis.VisualizationError, "COMPARISON_EXCEPTION_REASON_REQUIRED"):
            vis.build_plan(self.args(isovalue=0.04, comparison_manifest=str(baseline), allow_comparison_exception=True))
        plan = vis.build_plan(self.args(isovalue=0.04, comparison_manifest=str(baseline), allow_comparison_exception=True, comparison_exception_reason="intentional exploratory figure"))
        self.assertTrue(plan["comparison"]["exception_approved"])

    def test_source_stem_mismatch_is_a_hard_gate(self):
        other = self.work / "different.gbw"; other.write_bytes(b"other")
        with self.assertRaisesRegex(vis.VisualizationError, "SOURCE_IDENTITY_MISMATCH"):
            vis.build_plan(self.args(gbw=str(other)))

    def test_orca_plot_backend_is_hard_gated_to_orca_61(self):
        output = self.work / "job.out"
        output.write_text(OUT.replace("6.1.0", "6.0.0"))
        with self.assertRaisesRegex(vis.VisualizationError, "ORCA61_REQUIRED"):
            vis.build_plan(self.args())

    def test_input_source_mismatch_is_a_hard_gate(self):
        other = self.work / "other.inp"; other.write_text("# @FUNCTIONAL: PBE0\n")
        with self.assertRaisesRegex(vis.VisualizationError, "SOURCE_IDENTITY_MISMATCH"):
            vis.build_plan(self.args(input=str(other)))

    def test_missing_input_source_is_a_clear_gate(self):
        with self.assertRaisesRegex(vis.VisualizationError, "INPUT_SOURCE_NOT_FOUND"):
            vis.build_plan(self.args(input=str(self.work / "job.inp.missing")))

    def test_empty_orbital_request_is_rejected(self):
        with self.assertRaisesRegex(vis.VisualizationError, "ORBITAL_SELECTION_REQUIRED"):
            vis.build_plan(self.args(orbitals=""))

    def test_empty_view_request_is_rejected(self):
        with self.assertRaisesRegex(vis.VisualizationError, "VIEW_REQUIRED"):
            vis.build_plan(self.args(views=""))

    def test_cube_xyz_binding_checks_coordinates(self):
        cube = self.work / "job.mo1a.cube"
        cube.write_text("cube\ncube\n 3 0 0 0\n 2 1 0 0\n 2 0 1 0\n 2 0 0 1\n 6 0 0 0 0\n 6 0 1.889726 0 0\n 6 0 0 1.889726 0\n")
        binding = vis.verify_cube_xyz(cube, self.work / "job.xyz")
        self.assertEqual(binding["status"], "VERIFIED")
        cube.write_text(cube.read_text().replace("1.889726 0 0", "10 0 0"))
        with self.assertRaisesRegex(vis.VisualizationError, "CUBE_XYZ_MISMATCH"):
            vis.verify_cube_xyz(cube, self.work / "job.xyz")

        cube.write_text(cube.read_text().replace("10 0 0", "1.889726 0 0").replace(" 6 0 0 0 0", " 8 0 0 0 0"))
        with self.assertRaisesRegex(vis.VisualizationError, "CUBE_XYZ_ELEMENT_MISMATCH"):
            vis.verify_cube_xyz(cube, self.work / "job.xyz")

    def test_vmd_replaces_old_derived_artifacts_and_accepts_deterministic_output(self):
        script, tga, png = self.work / "render.tcl", self.work / "old.tga", self.work / "new.png"
        script.write_text("quit\n"); tga.write_text("same tga"); png.write_text("same png")

        def fake_run(command, **kwargs):
            if command == ["vmd", "-version"]:
                return SimpleNamespace(stdout="VMD 1.9", returncode=0)
            if command[:2] == ["vmd", "-dispdev"]:
                self.assertFalse(tga.exists()); self.assertFalse(png.exists())
                tga.write_text("same tga")
                return SimpleNamespace(stdout="", returncode=0)
            if command == ["magick", "-version"]:
                return SimpleNamespace(stdout="ImageMagick 7", returncode=0)
            self.assertEqual(command[0], "magick")
            png.write_text("same png")
            return SimpleNamespace(stdout="", returncode=0)

        with patch.object(vis.shutil, "which", side_effect=lambda name: "magick" if name == "magick" else None), patch.object(vis.subprocess, "run", side_effect=fake_run):
            result = vis.run_vmd(script, tga, png, "vmd", 10)
        self.assertEqual(result["status"], "RENDERED")
        self.assertTrue(result["tga_previous_sha256"])
        self.assertTrue(result["png_previous_sha256"])


if __name__ == "__main__":
    unittest.main()
