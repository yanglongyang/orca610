import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import orbital_visualize as vis
import orbital_cube_orca as cube


CLOSED = """
ORBITAL ENERGIES
----------------
  NO   OCC          E(Eh)            E(eV)
   0  2.0000   -0.5000000      -13.6057
   1  2.0000   -0.3000000       -8.1634
   2  2.0000   -0.1000000       -2.7211
Occupied Orbitals Manifold
   3  0.0000    0.0500000        1.3606
Unoccupied Orbitals Manifold
   4  0.0000    0.1000000        2.7211
ORCA TERMINATED NORMALLY
"""

OPEN = """
SPIN UP ORBITALS
ORBITAL ENERGIES
  NO   OCC          E(Eh)            E(eV)
   0  1.0000   -0.5000000      -13.6057
   1  1.0000   -0.1000000       -2.7211
   2  0.0000    0.0500000        1.3606
SPIN DOWN ORBITALS
ORBITAL ENERGIES
  NO   OCC          E(Eh)            E(eV)
   0  1.0000   -0.4500000      -12.2451
   1  0.0000    0.0200000        0.5442
"""


class OrbitalParserTests(unittest.TestCase):
    def test_frontier_indices_for_closed_shell(self):
        channels = vis.parse_orbitals(CLOSED)
        self.assertEqual(list(channels), ["restricted"])
        homo, lumo = vis.frontier_orbitals(channels["restricted"])
        self.assertEqual((homo.index, lumo.index), (2, 3))
        selected = vis.resolve_orbitals(channels, ["HOMO-1", "LUMO+1"], None, False)
        self.assertEqual([item.orbital.index for item in selected], [1, 4])
        self.assertEqual([item.operator for item in selected], [0, 0])

    def test_open_shell_requires_explicit_spin_or_all_spins(self):
        channels = vis.parse_orbitals(OPEN)
        with self.assertRaisesRegex(vis.VisualizationError, "SPIN_CHANNEL_REQUIRED"):
            vis.resolve_orbitals(channels, ["HOMO", "LUMO"], None, False)
        beta = vis.resolve_orbitals(channels, ["HOMO", "LUMO"], "beta", False)
        self.assertEqual([item.orbital.index for item in beta], [0, 1])
        self.assertEqual([item.operator for item in beta], [1, 1])
        both = vis.resolve_orbitals(channels, ["HOMO"], None, True)
        self.assertEqual({item.label for item in both}, {"HOMO_alpha", "HOMO_beta"})

    def test_orca_plot_answers_use_zero_based_mo_and_requested_operator(self):
        answers = cube.mo_plot_answers(78, 1, 100).splitlines()
        self.assertEqual(answers, ["1", "1", "2", "78", "3", "1", "4", "100", "5", "7", "8", "0", "11", "12"])


if __name__ == "__main__":
    unittest.main()
