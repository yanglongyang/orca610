import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import state_gate


class StateGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.work = Path(self.temp.name)
        self.manifest = self.work / "state_gates.json"
        self.vertical_input = self.work / "r0.inp"; self.vertical_input.write_text("! CAM-B3LYP\n%tddft\n nroots 3\nend\n")
        self.vertical_output = self.work / "r0.out"; self.vertical_output.write_text("ORCA TERMINATED NORMALLY\n")
        self.opt_input = self.work / "s1.inp"; self.opt_input.write_text("! Opt CAM-B3LYP\n%tddft\n nroots 3\nend\n")
        self.opt_output = self.work / "s1.out"; self.opt_output.write_text("ORCA TERMINATED NORMALLY\n")

    def tearDown(self): self.temp.cleanup()

    def args(self, **values):
        defaults = {"manifest": str(self.manifest), "species": "MOL1", "vertical_input": str(self.vertical_input), "vertical_output": str(self.vertical_output), "root": 2, "state_character": "ICT", "selection_basis": ["NTO", "oscillator_strength"], "opt_input": str(self.opt_input), "opt_output": str(self.opt_output), "final_root": 3, "evidence": ["NTO", "excitation_energy"]}
        defaults.update(values); return SimpleNamespace(**defaults)

    def test_selection_and_identity_are_hash_bound(self):
        state_gate.select(self.args())
        self.assertEqual(state_gate.require_selection(self.args())["selected_root"], 2)
        state_gate.confirm(self.args())
        self.assertEqual(state_gate.require_identity(self.args())["final_root"], 3)
        self.opt_output.write_text("changed\nORCA TERMINATED NORMALLY\n")
        with self.assertRaises(state_gate.StateGateError): state_gate.require_identity(self.args())

    def test_selection_requires_normal_vertical_output(self):
        self.vertical_output.write_text("failed\n")
        with self.assertRaises(state_gate.StateGateError): state_gate.select(self.args())

    def test_roots_must_be_within_input_nroots(self):
        with self.assertRaises(state_gate.StateGateError): state_gate.select(self.args(root=4))
        state_gate.select(self.args())
        with self.assertRaises(state_gate.StateGateError): state_gate.confirm(self.args(final_root=4))
