import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import orbital_cube_orca as cube


class OrcaCubeBackendTests(unittest.TestCase):
    def test_mocked_orca_plot_generates_and_moves_expected_cube_with_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            gbw, destination = work / "job.gbw", work / "visualization" / "HOMO.cube"
            gbw.write_bytes(b"placeholder")

            def fake_run(command, **kwargs):
                self.assertEqual(command[-2:], ["job.gbw", "-i"])
                self.assertEqual(kwargs["timeout"], 37)
                self.assertIn("\n1\n", kwargs["input"])
                (work / "job.mo78a.cube").write_text("cube")
                return SimpleNamespace(returncode=0, stdout="orca_plot completed")

            with patch.object(cube, "find_orca_plot", return_value="orca_plot"), patch.object(cube.subprocess, "run", side_effect=fake_run):
                result = cube.generate_cube(gbw, 78, 0, destination, 100, timeout_seconds=37)
            self.assertTrue(destination.is_file())
            self.assertEqual(result["timeout_seconds"], 37)

    def test_orca_plot_timeout_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            gbw = Path(temporary) / "job.gbw"; gbw.write_bytes(b"placeholder")
            with patch.object(cube, "find_orca_plot", return_value="orca_plot"), patch.object(cube.subprocess, "run", side_effect=__import__("subprocess").TimeoutExpired("orca_plot", 2)):
                with self.assertRaisesRegex(cube.OrcaPlotError, "exceeded 2s"):
                    cube.generate_cube(gbw, 1, 0, Path(temporary) / "out.cube", 100, timeout_seconds=2)

    def test_unchanged_old_cube_is_never_reused_after_success_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            gbw = work / "job.gbw"; gbw.write_bytes(b"placeholder")
            (work / "job.mo78a.cube").write_text("old cube")
            with patch.object(cube, "find_orca_plot", return_value="orca_plot"), patch.object(cube.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="success")):
                with self.assertRaisesRegex(cube.OrcaPlotError, "no new or modified MO cube"):
                    cube.generate_cube(gbw, 78, 0, work / "out.cube", 100)


if __name__ == "__main__":
    unittest.main()
