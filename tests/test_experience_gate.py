import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import experience_gate


class ExperienceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.work = Path(self.temp.name)
        self.input = self.work / "job.inp"; self.manifest = self.work / "experience_checks.json"
        self.old_rules = os.environ.get("AUTOORCA_KNOWLEDGE_RULES")
        os.environ["AUTOORCA_KNOWLEDGE_RULES"] = str(ROOT / "knowledge" / "rules")

    def tearDown(self):
        if self.old_rules is None: os.environ.pop("AUTOORCA_KNOWLEDGE_RULES", None)
        else: os.environ["AUTOORCA_KNOWLEDGE_RULES"] = self.old_rules
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
        args = SimpleNamespace(input=str(self.input), output=str(output), pattern="INPUT ERROR", case_dir=str(case_dir))
        record = json.loads(experience_gate.record_failure(args).read_text())
        self.assertEqual(record["evidence_level"], "LOCAL_OBSERVATION")
        self.assertIn("INPUT ERROR", record["output_tail"])
