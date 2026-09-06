#!/usr/bin/env python3
"""Generate a molecular-orbital Gaussian cube with ORCA's ``orca_plot``.

The interactive menu sequence is the documented ORCA 6.1 MO/Cube route.  It
is intentionally isolated here: the visualizer can plan a job without running
external programs, while this module owns the small, version-sensitive bridge.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class OrcaPlotError(RuntimeError):
    """Raised when ORCA's post-processing utility cannot make a cube."""


def mo_plot_answers(orbital_index: int, operator: int, grid: int) -> str:
    """Return the ORCA 6.1 interactive answers for an MO Gaussian Cube plot."""
    if orbital_index < 0 or operator not in (0, 1) or grid < 10:
        raise ValueError("orbital index/operator/grid is invalid")
    # Main menu: plot type -> molecular orbital; then set MO/operator/grid,
    # select Gaussian Cube (format 7), MO (not AO), generate, exit.
    return f"1\n1\n2\n{orbital_index}\n3\n{operator}\n4\n{grid}\n5\n7\n8\n0\n11\n12\n"


def find_orca_plot(explicit: str | None = None) -> str | None:
    """Resolve an explicit path or a PATH-visible ``orca_plot`` executable."""
    if explicit:
        path = Path(explicit).expanduser()
        return str(path) if path.is_file() else None
    return shutil.which("orca_plot")


def _candidate_cubes(directory: Path, stem: str, orbital: int, operator: int) -> list[Path]:
    suffix = "a" if operator == 0 else "b"
    preferred = directory / f"{stem}.mo{orbital}{suffix}.cube"
    candidates = [preferred] if preferred.is_file() else []
    candidates.extend(
        item for item in directory.glob("*.cube")
        if item not in candidates and f"mo{orbital}{suffix}" in item.name.lower()
    )
    return candidates


def generate_cube(
    gbw: Path,
    orbital_index: int,
    operator: int,
    output_cube: Path,
    grid: int,
    orca_plot: str | None = None,
    timeout_seconds: int = 600,
) -> dict:
    """Run ``orca_plot`` and move its generated cube to ``output_cube``."""
    gbw = gbw.resolve()
    if not gbw.is_file():
        raise OrcaPlotError(f"GBW file does not exist: {gbw}")
    executable = find_orca_plot(orca_plot)
    if not executable:
        raise OrcaPlotError("orca_plot was not found; supply --orca-plot or add it to PATH")
    workdir = gbw.parent
    before = {item.resolve() for item in workdir.glob("*.cube")}
    try:
        result = subprocess.run(
            [executable, gbw.name, "-i"], cwd=workdir, input=mo_plot_answers(orbital_index, operator, grid),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise OrcaPlotError(f"orca_plot exceeded {timeout_seconds}s and was terminated") from exc
    except OSError as exc:
        raise OrcaPlotError(f"orca_plot could not start: {exc}") from exc
    if result.returncode != 0:
        raise OrcaPlotError(f"orca_plot failed ({result.returncode}):\n{result.stdout[-2000:]}")
    candidates = _candidate_cubes(workdir, gbw.stem, orbital_index, operator)
    new = [item for item in candidates if item.resolve() not in before]
    source = (new or candidates)
    if not source:
        raise OrcaPlotError("orca_plot ended without producing the expected MO cube")
    output_cube.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source[0]), str(output_cube))
    return {"command": [executable, gbw.name, "-i"], "timeout_seconds": timeout_seconds, "stdout_tail": result.stdout[-2000:], "cube": str(output_cube)}
