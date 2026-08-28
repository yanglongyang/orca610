import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import input_approve
import input_review


class InputReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.manifest = self.work / "input_reviews.json"
        self.xyz = self.work / "geometry.xyz"
        self.xyz.write_text("2\nfixture\nH 0 0 0\nH 0 0 0.7\n")
        self.input = self.work / "job.inp"
        self.input.write_text(
            "# fixture vertical excitation\n! CAM-B3LYP def2-SVPD CPCM(Water) TightScf\n"
            "%pal\n nprocs 2\nend\n%tddft\n nroots 3\n iroot 1\n tda false\n donto true\n ntostates 1\nend\n"
            "* xyzfile 0 1 geometry.xyz\n"
        )

    def tearDown(self):
        self.temp.cleanup()

    def _review_and_approve(self):
        input_review.review(self.input, self.manifest, "vertical_absorption")
        return input_approve.approve(self.input, self.manifest)

    def test_unapproved_input_is_refused(self):
        input_review.review(self.input, self.manifest, "vertical_absorption")
        with self.assertRaises(input_review.ReviewError):
            input_review.require(self.input, self.manifest)

    def test_approved_unchanged_input_passes(self):
        self._review_and_approve()
        record = input_review.require(self.input, self.manifest)
        self.assertEqual(record["status"], "APPROVED")

    def test_rejected_input_cannot_run(self):
        input_review.review(self.input, self.manifest, "vertical_absorption")
        record = input_review.reject(self.input, self.manifest)
        self.assertEqual(record["status"], "REJECTED")
        with self.assertRaises(input_review.ReviewError):
            input_review.require(self.input, self.manifest)

    def test_historical_completed_output_is_marked_imported_not_preapproved(self):
        record = input_review.review(self.input, self.manifest, "vertical_absorption", existing_completed_output=True)
        self.assertEqual(record["status"], "REVIEW_REQUIRED")
        self.assertEqual(record["execution_provenance"], "IMPORTED_UNREVIEWED")
        self.assertIn("IMPORTED_UNREVIEWED", input_review._render(record))

    def test_approved_input_records_running_then_completed(self):
        self._review_and_approve()
        running = input_review.mark_state(self.input, self.manifest, "RUNNING")
        completed = input_review.mark_state(self.input, self.manifest, "COMPLETED")
        self.assertEqual(running["status"], "RUNNING")
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(input_review.require(self.input, self.manifest)["status"], "COMPLETED")

    def test_input_change_invalidates_approval(self):
        self._review_and_approve()
        self.input.write_text(self.input.read_text().replace("CAM-B3LYP", "PBE0"))
        with self.assertRaises(input_review.ReviewError):
            input_review.require(self.input, self.manifest)
        record = json.loads(self.manifest.read_text())["inputs"][str(self.input.resolve())]
        self.assertEqual(record["status"], "REVIEW_REQUIRED")
        self.assertEqual(record["history"][-1]["status"], "INVALIDATED")

    def test_xyz_change_invalidates_approval(self):
        self._review_and_approve()
        self.xyz.write_text(self.xyz.read_text().replace("0.7", "0.8"))
        with self.assertRaises(input_review.ReviewError):
            input_review.require(self.input, self.manifest)

    def test_hessian_change_invalidates_approval(self):
        gs, es = self.work / "gs.hess", self.work / "es.hess"
        gs.write_text("gs before\n"); es.write_text("es before\n")
        self.input.write_text(
            "! CAM-B3LYP def2-SVP ESD(IC)\n%esd\n gshessian \"gs.hess\"\n eshessian \"es.hess\"\nend\n* xyz 0 1\nH 0 0 0\n*\n"
        )
        self._review_and_approve()
        es.write_text("es after\n")
        with self.assertRaises(input_review.ReviewError):
            input_review.require(self.input, self.manifest)

    def test_regenerated_input_returns_to_review_required(self):
        self._review_and_approve()
        self.input.write_text(self.input.read_text() + "# regenerated\n")
        record = input_review.review(self.input, self.manifest, "vertical_absorption")
        self.assertEqual(record["status"], "REVIEW_REQUIRED")

    def test_template_instantiation_requires_its_own_review(self):
        template = self.work / "verified_template.inp"
        template.write_text("! PBE0 def2-SVP\n* xyz 0 1\nH 0 0 0\n*\n")
        instantiated = self.work / "molecule_from_template.inp"
        instantiated.write_text(template.read_text().replace("H 0 0 0", "H 0 0 0.1"))
        input_review.review(instantiated, self.manifest, "template_instance")
        with self.assertRaises(input_review.ReviewError):
            input_review.require(instantiated, self.manifest)

    def test_review_warns_about_project_protocol_and_electronic_state_changes(self):
        input_review.review(self.input, self.manifest, "vertical_absorption")
        comparison = self.work / "comparison.inp"
        comparison.write_text(
            "! PBE0 def2-TZVP D4 CPCM(Water)\n"
            "%tddft\n cpcmeq true\nend\n* xyzfile 1 2 geometry.xyz\n"
        )
        record = input_review.review(comparison, self.manifest, "vertical_absorption")
        warning_text = "\n".join(record["warnings"])
        self.assertIn("CPCMEQ true", warning_text)
        self.assertIn("project protocol differs", warning_text)
        self.assertIn("charge/multiplicity differs", warning_text)

    def test_review_warns_about_esd_geometry_hessian_provenance_mismatch(self):
        (self.work / "probe_S1.xyz").write_text("1\nfixture\nH 0 0 0\n")
        (self.work / "probe_S0.hess").write_text("gs\n")
        (self.work / "probe_S1.hess").write_text("es\n")
        self.input.write_text(
            "! CAM-B3LYP def2-SVP ESD(IC)\n%esd\n gshessian probe_S0.hess\n eshessian probe_S1.hess\nend\n"
            "* xyzfile 0 1 probe_S1.xyz\n"
        )
        record = input_review.review(self.input, self.manifest, "esd_ic")
        self.assertIn("geometry provenance appears to be S1", "\n".join(record["warnings"]))
        self.assertIn("GSHessian (S0) provenance markers differ", "\n".join(record["warnings"]))


if __name__ == "__main__":
    unittest.main()
