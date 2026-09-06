import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import orbital_visualize as vis


class OrbitalViewTests(unittest.TestCase):
    def test_planar_geometry_uses_plane_normal_for_front(self):
        points = [(-3, 0, 0), (-1, 1, 0), (1, -1, 0), (3, 0, 0)]
        pca = vis.pca_axes(points)
        normal = pca["smallest"]
        self.assertAlmostEqual(abs(normal[2]), 1.0, places=7)
        self.assertAlmostEqual(normal[0], 0.0, places=7)
        matrix = vis.camera_matrix(normal, pca["largest"])
        self.assertEqual(len(matrix), 16)
        self.assertAlmostEqual(math.sqrt(sum(item*item for item in matrix[8:11])), 1.0, places=7)

    def test_explicit_axis_override(self):
        pca = {"smallest": (0, 0, 1), "middle": (0, 1, 0), "largest": (1, 0, 0)}
        self.assertEqual(vis.axis_from_name("x", pca), (1.0, 0.0, 0.0))
        self.assertEqual(vis.axis_from_name("middle", pca), (0, 1, 0))

    def test_parallel_reference_axis_uses_a_non_parallel_fallback(self):
        matrix = vis.camera_matrix((1.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        self.assertEqual(len(matrix), 16)
        self.assertAlmostEqual(math.sqrt(sum(item*item for item in matrix[0:3])), 1.0, places=7)

    def test_matrix_tcl_is_nested_four_by_four(self):
        encoded = vis.matrix_tcl([1.0, 0.0, 0.0, 0.0] * 4)
        self.assertEqual(encoded, "{{{1 0 0 0} {1 0 0 0} {1 0 0 0} {1 0 0 0}}}")


if __name__ == "__main__":
    unittest.main()
