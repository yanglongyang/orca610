import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "scripts" / "shared_functions.sh"


class RunnerLockingTests(unittest.TestCase):
    def bash(self) -> str | None:
        return shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if Path(r"C:\Program Files\Git\bin\bash.exe").exists() else None)

    def test_pid_lock_is_input_scoped_and_never_greps_global_processes(self):
        text = SHARED.read_text(encoding="utf-8")
        self.assertNotIn("ps aux", text)
        self.assertIn("job_lock_file", text)
        self.assertIn('input=$(realpath "$input")', text)

        bash = self.bash()
        if not bash:
            self.skipTest("bash is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            # The path intentionally contains 'orca'; both projects reuse basename.
            first = work / "orca-install-path" / "one" / "phase4_s1freq.inp"
            second = work / "orca-install-path" / "two" / "phase4_s1freq.inp"
            first.parent.mkdir(parents=True); second.parent.mkdir(parents=True)
            first.write_text("! CAM-B3LYP\n"); second.write_text("! CAM-B3LYP\n")
            script = r'''
set -e
export PATH="/usr/bin:/bin:$PATH"
export AUTOORCA_WORKDIR="$(dirname "$2")"
export ORCA_ROOT="$(dirname "$2")/missing-orca"
source "$1"
one="$(realpath "$2")"; two="$(realpath "$3")"
! job_running "$one"
bash -c 'sleep 5; :' "$one" & worker=$!
write_job_lock "$one" "$worker"
job_running "$one"
! job_running "$two"
kill "$worker"; wait "$worker" 2>/dev/null || true
! job_running "$one"
'''
            result = subprocess.run([bash, "-c", script, "--", str(SHARED), first.as_posix(), second.as_posix()], text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
