import sys
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fluorescence_probe_report as report
import tict_scan_builder as tict


class TictDiagnosticsTests(unittest.TestCase):
    def test_twist_alone_is_not_supported(self):
        self.assertNotEqual(
            tict.classify_tict({"geometry_compared": True, "substantial_twist": True}),
            "TICT_SUPPORTED",
        )

    def test_ict_needs_state_identity_evidence(self):
        result = report.classify_ict({
            "species": "probe",
            "state": "root_1",
            "qualitative_label": "STRONG_CT",
            "state_identity_verified": False,
            "donor_description": "donor fragment",
            "acceptor_description": "acceptor fragment",
        })
        self.assertEqual(result["qualitative_label"], "UNRESOLVED")

    def test_scan_builder_uses_zero_based_orca_dihedral_indices(self):
        text = tict.build_input({
            "xyz": str(ROOT / "examples" / "probe_S1.xyz"), "charge": 0, "multiplicity": 1,
            "atom_index_base": 1, "dihedral": [1, 2, 5, 6],
            "scan": {"start_deg": 0, "end_deg": 90, "n_steps": 10},
            "method": {
                "functional": "CAM-B3LYP", "basis": "def2-SVPD",
                "dispersion": "D3BJ", "solvent": "CPCM(Water)",
                "nroots": 5, "iroot": 1, "tda": False,
            },
        })
        self.assertIn("Scan D 0 1 4 5 = 0, 90, 10 end", text)
        self.assertIn("donto true", text)

    def test_scan_builder_rejects_an_atom_outside_xyz(self):
        with self.assertRaises(tict.TictInputError):
            tict.build_input({
                "xyz": str(ROOT / "examples" / "probe_S1.xyz"), "charge": 0, "multiplicity": 1,
                "atom_index_base": 1, "dihedral": [1, 2, 5, 99],
                "scan": {"start_deg": 0, "end_deg": 90, "n_steps": 10},
                "method": {"functional": "CAM-B3LYP", "basis": "def2-SVPD", "dispersion": "D3BJ", "solvent": "CPCM(Water)", "nroots": 5, "iroot": 1, "tda": False},
            })

    def test_homo_lumo_gap_alone_is_not_supported_mechanism(self):
        verdict = report.classify_mechanism([
            {"descriptor": "homo_lumo_gap", "assessment": "supportive"}
        ])
        self.assertEqual(verdict, "INSUFFICIENT")

    def test_repeated_spectral_evidence_cannot_be_supported(self):
        verdict = report.classify_mechanism([
            {"descriptor": "absorption_red_shift", "evidence_family": "spectral", "assessment": "strong"},
            {"descriptor": "emission_red_shift", "evidence_family": "spectral", "assessment": "supportive"},
        ])
        self.assertEqual(verdict, "PLAUSIBLE")

    def test_independent_evidence_families_can_be_supported(self):
        verdict = report.classify_mechanism([
            {"descriptor": "NTO", "evidence_family": "NTO", "assessment": "strong"},
            {"descriptor": "emission_red_shift", "evidence_family": "spectral", "assessment": "supportive"},
        ])
        self.assertEqual(verdict, "SUPPORTED")

    def test_report_preserves_evidence_levels(self):
        payload, markdown = report.build_report({
            "project": "test_probe",
            "pair_comparison": {"comparison_gate": "PASS"},
            "nto_evidence": [{
                "species": "probe", "state": "S1_R0",
                "qualitative_label": "PARTIAL_CT",
                "state_identity_verified": True,
                "donor_description": "donor", "acceptor_description": "acceptor",
            }],
            "mechanism_hypotheses": [{
                "hypothesis": "ICT restoration",
                "evidence": [{"descriptor": "NTO", "assessment": "strong"}],
            }],
        })
        self.assertEqual(payload["nto_ict_analysis"][0]["qualitative_label"], "PARTIAL_CT")
        self.assertEqual(payload["mechanistic_interpretation"][0]["verdict"], "PLAUSIBLE")
        self.assertIn("Fluorescence Probe Photophysics Report", markdown)

    def test_invalid_multiwfn_path_is_not_available(self):
        with mock.patch.dict("os.environ", {"MULTIWFN_BIN": "definitely-not-a-real-multiwfn-binary"}):
            self.assertEqual(report.multiwfn_status()["status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
