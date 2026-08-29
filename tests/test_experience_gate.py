import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import experience_gate


class ExperienceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.work = Path(self.temp.name)
        self.input = self.work / "job.inp"; self.manifest = self.work / "experience_checks.json"
        self.old_rules = os.environ.get("AUTOORCA_KNOWLEDGE_RULES")
        self.old_cases = os.environ.get("AUTOORCA_EXPERIENCE_CASE_DIR")
        os.environ["AUTOORCA_KNOWLEDGE_RULES"] = str(ROOT / "knowledge" / "rules")
        os.environ["AUTOORCA_EXPERIENCE_CASE_DIR"] = str(self.work / "experience" / "cases" / "failure")

    def tearDown(self):
        if self.old_rules is None: os.environ.pop("AUTOORCA_KNOWLEDGE_RULES", None)
        else: os.environ["AUTOORCA_KNOWLEDGE_RULES"] = self.old_rules
        if self.old_cases is None: os.environ.pop("AUTOORCA_EXPERIENCE_CASE_DIR", None)
        else: os.environ["AUTOORCA_EXPERIENCE_CASE_DIR"] = self.old_cases
        self.temp.cleanup()

    def test_known_invalid_tddft_simple_keyword_is_refused(self):
        self.input.write_text("! Opt TDDFT CAM-B3LYP def2-SVP\n")
        with self.assertRaises(experience_gate.ExperienceError) as caught:
            experience_gate.check(self.input, self.manifest, "s1_opt")
        self.assertIn("ORCA61-TDDFT-001", str(caught.exception))

    def test_valid_tddft_block_is_checked_and_hash_bound(self):
        self.input.write_text("! Opt CAM-B3LYP def2-SVP\n%tddft\n iroot 1\nend\n")
        experience_gate.check(self.input, self.manifest, "s1_opt")
        self.assertEqual(experience_gate.require(self.input, self.manifest)["calculation_type"], "s1_opt")
        self.input.write_text(self.input.read_text() + "# changed\n")
        with self.assertRaises(experience_gate.ExperienceError): experience_gate.require(self.input, self.manifest)

    def test_runtime_failure_is_persisted_as_local_observation(self):
        self.input.write_text("! CAM-B3LYP\n")
        output = self.work / "job.out"; output.write_text("INPUT ERROR\n")
        case_dir = self.work / "experience" / "cases" / "failure"
        args = SimpleNamespace(input=str(self.input), output=str(output), pattern="INPUT ERROR", case_dir=str(case_dir), orca_version="6.1.0")
        record = json.loads(experience_gate.record_failure(args).read_text())
        self.assertEqual(record["evidence_level"], "LOCAL_OBSERVATION")
        self.assertIn("INPUT ERROR", record["output_tail"])
        self.assertIn("input_text", record)
        self.assertIn("dependency_fingerprints", record)

    def test_exact_prior_failure_is_a_hard_refusal(self):
        self.input.write_text("# @ORCA: 6.1.0\n! CAM-B3LYP\n")
        output = self.work / "job.out"; output.write_text("INPUT ERROR\n")
        case_dir = self.work / "experience" / "cases" / "failure"
        experience_gate.record_failure(SimpleNamespace(input=str(self.input), output=str(output), pattern="INPUT ERROR", case_dir=str(case_dir), orca_version="6.1.0"))
        with self.assertRaises(experience_gate.ExperienceError) as caught:
            experience_gate.check(self.input, self.manifest, "s0_optfreq")
        self.assertIn("EXACT_REPEAT_LOCAL_FAILURE", str(caught.exception))

    def test_lookup_reads_the_evidence_index_before_generation(self):
        result = experience_gate.lookup("s1_opt")
        self.assertEqual(result["calculation_type"], "s1_opt")
        self.assertIn("experience_index_sha256", result)

    def test_standalone_manifest_default_is_input_scoped(self):
        self.assertEqual(experience_gate.resolve_manifest(self.input, None), self.input.parent / "experience_checks.json")

    def test_evidence_index_change_refreshes_unchanged_input(self):
        self.input.write_text("! CAM-B3LYP\n")
        original = experience_gate.check(self.input, self.manifest, "s0_optfreq")
        case_dir = Path(os.environ["AUTOORCA_EXPERIENCE_CASE_DIR"]); case_dir.mkdir(parents=True)
        (case_dir / "unrelated.json").write_text(json.dumps({"input_sha256": "unrelated", "orca_version": "6.1.0"}))
        refreshed = experience_gate.require(self.input, self.manifest)
        self.assertNotEqual(original["experience_index_sha256"], refreshed["experience_index_sha256"])
        self.assertIn("refreshed_at", refreshed)

    def test_dependency_change_is_related_warning_not_exact_failure(self):
        xyz = self.work / "geometry.xyz"; xyz.write_text("1\nold\nH 0 0 0\n")
        self.input.write_text("# @ORCA: 6.1.0\n! CAM-B3LYP\n* xyzfile 0 1 geometry.xyz\n")
        output = self.work / "job.out"; output.write_text("INPUT ERROR\n")
        case_dir = self.work / "experience" / "cases" / "failure"
        experience_gate.record_failure(SimpleNamespace(input=str(self.input), output=str(output), pattern="INPUT ERROR", case_dir=str(case_dir), orca_version="6.1.0"))
        xyz.write_text("1\nrepaired\nH 0 0 0.1\n")
        result = experience_gate.check(self.input, self.manifest, "s0_optfreq")
        self.assertFalse(result["failures"])
        self.assertTrue(result["similar_observations"])

    def test_new_similar_failure_requires_explicit_acknowledgement(self):
        prefix = "! CAM-B3LYP\n%pal\n nprocs 2\nend\n# " + "x" * 200
        self.input.write_text(prefix + " current run\n")
        experience_gate.check(self.input, self.manifest, "s0_optfreq")
        output = self.work / "failed.out"; output.write_text("INPUT ERROR\n")
        case_dir = self.work / "experience" / "cases" / "failure"
        for index in range(6):
            failed_input = self.work / f"failed_{index}.inp"
            failed_input.write_text(prefix + f" failed run {index}\n")
            experience_gate.record_failure(SimpleNamespace(input=str(failed_input), output=str(output), pattern="INPUT ERROR", case_dir=str(case_dir), orca_version="6.1.0"))
        with self.assertRaises(experience_gate.ExperienceError) as caught:
            experience_gate.require(self.input, self.manifest)
        self.assertIn("EXPERIENCE_WARNING_ACK_REQUIRED", str(caught.exception))
        self.assertIn("Similar project-local failures", str(caught.exception))
        self.assertIn("6 total", str(caught.exception))
        self.assertIn("failed_5.json", str(caught.exception))
        with self.assertRaises(experience_gate.ExperienceError):
            experience_gate.acknowledge(self.input, self.manifest, False)
        acknowledged = experience_gate.acknowledge(self.input, self.manifest, True)
        self.assertEqual(acknowledged["acknowledged_by"], "human")
        self.assertIn("acknowledged_at", acknowledged)
        self.assertEqual(len(acknowledged["acknowledged_similar_observations"]), 6)
        self.assertEqual(experience_gate.require(self.input, self.manifest)["input_path"], str(self.input.resolve()))

    def test_detects_orca_version_when_not_configured(self):
        with patch.dict(os.environ, {"ORCA_VERSION": ""}), patch.object(experience_gate.shutil, "which", return_value="/opt/orca/orca"), patch.object(experience_gate.subprocess, "run", return_value=SimpleNamespace(stdout="Program Version 6.1.7\n")):
            self.assertEqual(experience_gate.detected_orca_version(), "6.1.7")

    def test_recorded_output_version_is_bound_to_current_input_hash(self):
        status = self.work / "cascade_status.json"
        self.input.write_text("! CAM-B3LYP\n")
        status.write_text(json.dumps({"runtime_provenance": {"orca_versions": {str(self.input.resolve()): {"input_sha256": experience_gate.sha256(self.input), "actual": "6.1.0"}}}}))
        with patch.dict(os.environ, {"AUTOORCA_STATUS_FILE": str(status)}):
            self.assertEqual(experience_gate.recorded_actual_orca_version(self.input), "6.1.0")
            self.input.write_text("! PBE0\n")
            self.assertIsNone(experience_gate.recorded_actual_orca_version(self.input))
