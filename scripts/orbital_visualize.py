#!/usr/bin/env python3
"""Create reproducible ORCA MO visualization plans and, on request, images.

This is deliberately a post-processing tool.  Without ``--execute`` it writes
only a plan, Tcl files, manifest, and summary; with ``--execute`` it invokes
the ORCA utility and optional VMD/ImageMagick tools.  It never writes ORCA
input or starts ORCA electronic-structure jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from orbital_cube_orca import OrcaPlotError, generate_cube

EPS = 1.0e-7
PROFILE_RESOLUTIONS = {"preview": (1200, 900), "publication": (3000, 2400)}


class VisualizationError(ValueError):
    """Raised for a non-reproducible or scientifically ambiguous request."""


@dataclass(frozen=True)
class Orbital:
    index: int
    occupation: float
    energy_hartree: float | None
    energy_ev: float | None
    spin: str


@dataclass(frozen=True)
class RequestedOrbital:
    label: str
    orbital: Orbital
    operator: int


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_record(path: Path | None) -> dict | None:
    if path is None:
        return None
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def _float(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def parse_orbitals(output_text: str) -> dict[str, list[Orbital]]:
    """Parse ORCA orbital-energy tables into restricted or alpha/beta channels."""
    channels: dict[str, list[Orbital]] = {}
    current_spin = "restricted"
    active = False
    # ORCA prints variants such as "SPIN UP ORBITALS" and "SPIN DOWN ORBITALS".
    row = re.compile(
        r"^\s*(\d+)\s+([-+0-9.]+)\s+([-+0-9.DEde]+)(?:\s+([-+0-9.DEde]+))?\s*$"
    )
    for line in output_text.splitlines():
        upper = line.upper()
        if "SPIN UP" in upper or "ALPHA ORBIT" in upper:
            current_spin = "alpha"; active = False; continue
        if "SPIN DOWN" in upper or "BETA ORBIT" in upper:
            current_spin = "beta"; active = False; continue
        if "ORBITAL ENERGIES" in upper:
            active = True; continue
        if not active:
            continue
        match = row.match(line)
        if not match:
            # Headers/separators are allowed; a substantive new section ends a table.
            if line.strip() and not set(line.strip()) <= {"-", "="} and not re.search(r"NO\s+OCC", upper):
                active = False
            continue
        index, occupation, e_h, e_ev = match.groups()
        channels.setdefault(current_spin, []).append(
            Orbital(int(index), _float(occupation), _float(e_h), _float(e_ev) if e_ev else None, current_spin)
        )
    if not channels:
        raise VisualizationError("no ORCA ORBITAL ENERGIES table was found in the output")
    for spin, values in channels.items():
        channels[spin] = sorted({item.index: item for item in values}.values(), key=lambda item: item.index)
    return channels


def frontier_orbitals(orbitals: list[Orbital]) -> tuple[Orbital, Orbital]:
    occupied = [item for item in orbitals if item.occupation > EPS]
    if not occupied:
        raise VisualizationError("orbital table has no occupied orbitals")
    homo = max(occupied, key=lambda item: item.index)
    unoccupied = [item for item in orbitals if item.index > homo.index and item.occupation <= EPS]
    if not unoccupied:
        raise VisualizationError(f"no unoccupied orbital follows {homo.index}")
    return homo, min(unoccupied, key=lambda item: item.index)


def _frontier_token(token: str, homo: Orbital, lumo: Orbital) -> Orbital:
    match = re.fullmatch(r"(HOMO|LUMO)([+-]\d+)?", token.upper())
    if not match:
        raise VisualizationError(f"unsupported orbital selector {token!r}; use HOMO, LUMO, HOMO-1, or LUMO+1")
    base, offset_text = match.groups()
    offset = int(offset_text or "0")
    target = (homo.index if base == "HOMO" else lumo.index) + offset
    return Orbital(target, 0.0, None, None, homo.spin)


def resolve_orbitals(
    channels: dict[str, list[Orbital]], selectors: list[str], spin: str | None, all_spins: bool
) -> list[RequestedOrbital]:
    """Resolve selectors without silently choosing a spin for an open shell."""
    open_shell = "alpha" in channels or "beta" in channels
    if open_shell and not (spin or all_spins):
        raise VisualizationError("SPIN_CHANNEL_REQUIRED: open-shell result needs --spin alpha/beta or --all-spins")
    if spin and all_spins:
        raise VisualizationError("use either --spin or --all-spins, not both")
    selected_spins = ([spin] if spin else sorted(channels)) if open_shell else ["restricted"]
    answer: list[RequestedOrbital] = []
    for channel in selected_spins:
        if channel not in channels:
            raise VisualizationError(f"requested spin {channel!r} is absent from the output")
        values = {item.index: item for item in channels[channel]}
        homo, lumo = frontier_orbitals(channels[channel])
        for selector in selectors:
            requested = _frontier_token(selector, homo, lumo)
            if requested.index not in values:
                raise VisualizationError(f"{selector} resolves to MO {requested.index}, absent from {channel} table")
            actual = values[requested.index]
            label = selector.upper().replace("+", "plus").replace("-", "minus")
            if open_shell:
                label = f"{label}_{channel}"
            answer.append(RequestedOrbital(label, actual, 0 if channel != "beta" else 1))
    return answer


def parse_xyz(path: Path) -> list[tuple[float, float, float]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        count = int(lines[0].strip())
    except (IndexError, ValueError) as exc:
        raise VisualizationError(f"invalid XYZ atom count: {path}") from exc
    points = []
    for line in lines[2:2 + count]:
        fields = line.split()
        if len(fields) < 4:
            raise VisualizationError(f"invalid XYZ coordinate line: {line!r}")
        points.append(tuple(float(value) for value in fields[1:4]))
    if len(points) != count:
        raise VisualizationError(f"XYZ declares {count} atoms but supplies {len(points)}")
    return points


def _normal(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm < 1.0e-12:
        raise VisualizationError("cannot construct a camera axis from a zero vector")
    return tuple(x / norm for x in vector)


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _jacobi_eigensystem(cov: list[list[float]]) -> tuple[list[float], list[tuple[float, float, float]]]:
    """Small dependency-free symmetric 3x3 eigensystem (Jacobi rotations)."""
    a = [row[:] for row in cov]
    vectors = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(64):
        p, q = max(((i, j) for i in range(3) for j in range(i + 1, 3)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1.0e-12:
            break
        angle = 0.5 * math.atan2(2*a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(angle), math.sin(angle)
        for k in range(3):
            if k not in (p, q):
                apk, aqk = a[p][k], a[q][k]
                a[p][k] = a[k][p] = c*apk - s*aqk
                a[q][k] = a[k][q] = s*apk + c*aqk
        app, aqq, apq = a[p][p], a[q][q], a[p][q]
        a[p][p] = c*c*app - 2*s*c*apq + s*s*aqq
        a[q][q] = s*s*app + 2*s*c*apq + c*c*aqq
        a[p][q] = a[q][p] = 0.0
        for k in range(3):
            vkp, vkq = vectors[k][p], vectors[k][q]
            vectors[k][p] = c*vkp - s*vkq
            vectors[k][q] = s*vkp + c*vkq
    pairs = sorted((a[i][i], _normal(tuple(vectors[k][i] for k in range(3)))) for i in range(3))
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def pca_axes(points: list[tuple[float, float, float]]) -> dict:
    if len(points) < 3:
        raise VisualizationError("at least three XYZ atoms are needed for PCA camera orientation")
    center = tuple(sum(point[i] for point in points) / len(points) for i in range(3))
    cov = [[sum((point[i]-center[i])*(point[j]-center[j]) for point in points) / len(points) for j in range(3)] for i in range(3)]
    eigenvalues, axes = _jacobi_eigensystem(cov)
    return {"centroid": center, "eigenvalues": eigenvalues, "smallest": axes[0], "middle": axes[1], "largest": axes[2]}


def axis_from_name(name: str, pca: dict) -> tuple[float, float, float]:
    fixed = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
    return fixed[name] if name in fixed else pca[name]


def camera_matrix(view_axis: tuple[float, float, float], reference_axis: tuple[float, float, float]) -> list[float]:
    z_axis = _normal(view_axis)
    x_axis = _cross(reference_axis, z_axis)
    if math.sqrt(sum(x*x for x in x_axis)) < 1.0e-8:
        x_axis = _cross((1.0, 0.0, 0.0), z_axis)
    x_axis = _normal(x_axis)
    y_axis = _normal(_cross(z_axis, x_axis))
    return [*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, 0.0, 0.0, 0.0, 1.0]


def output_version(text: str) -> str | None:
    match = re.search(r"(?:Program\s+)?Version\s*[:= ]+([^\s,;]+)", text, re.I)
    return match.group(1) if match else None


def input_metadata(path: Path | None) -> dict:
    if not path:
        return {}
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*#\s*@([A-Z_]+):\s*(.*?)\s*$", line, re.I)
        if match:
            data[match.group(1).lower()] = match.group(2)
    return data


def comparison_check(reference: Path | None, isovalue: float, profile: str, views: list[str], allow: bool) -> dict | None:
    if reference is None:
        return None
    other = json.loads(reference.read_text(encoding="utf-8"))
    render = other.get("render", {})
    differences = []
    if float(render.get("isovalue", -1)) != isovalue: differences.append("isovalue")
    if render.get("profile") != profile: differences.append("profile")
    if render.get("views") != views: differences.append("views")
    if render.get("camera_convention") != "PCA-or-explicit-axis-v1": differences.append("camera convention")
    if differences and not allow:
        raise VisualizationError("COMPARISON_CONVENTION_MISMATCH: " + ", ".join(differences))
    return {"reference_manifest": str(reference.resolve()), "differences": differences, "exception_approved": bool(differences and allow)}


def tcl_text(template: str, xyz: Path, cube: Path, tga: Path, isovalue: float, matrix: list[float], resolution: tuple[int, int]) -> str:
    replacements = {
        "{{XYZ}}": str(xyz.resolve()).replace("\\", "/"), "{{CUBE}}": str(cube.resolve()).replace("\\", "/"),
        "{{TGA}}": str(tga.resolve()).replace("\\", "/"), "{{ISOVALUE}}": f"{isovalue:.6g}",
        "{{ROTATE_MATRIX}}": "{" + " ".join(f"{item:.10g}" for item in matrix) + "}",
        "{{WIDTH}}": str(resolution[0]), "{{HEIGHT}}": str(resolution[1]),
    }
    for key, value in replacements.items(): template = template.replace(key, value)
    return template


def run_vmd(script: Path, tga: Path, png: Path, vmd: str | None) -> dict:
    executable = vmd or shutil.which("vmd")
    if not executable:
        return {"status": "VMD_NOT_AVAILABLE"}
    completed = subprocess.run([executable, "-dispdev", "text", "-e", str(script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if completed.returncode != 0 or not tga.is_file():
        return {"status": "VMD_FAILED", "stdout_tail": completed.stdout[-2000:]}
    converter = shutil.which("magick") or shutil.which("convert")
    if not converter:
        return {"status": "PNG_CONVERTER_NOT_AVAILABLE", "tga": str(tga)}
    converted = subprocess.run([converter, str(tga), str(png)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    return {"status": "RENDERED" if converted.returncode == 0 and png.is_file() else "PNG_CONVERSION_FAILED", "tga": str(tga), "png": str(png)}


def build_plan(args: argparse.Namespace) -> dict:
    out, gbw, xyz = Path(args.output).resolve(), Path(args.gbw).resolve(), Path(args.xyz).resolve()
    input_path = Path(args.input).resolve() if args.input else None
    for item in (out, gbw, xyz):
        if not item.is_file(): raise VisualizationError(f"required source does not exist: {item}")
    output_text = out.read_text(encoding="utf-8", errors="replace")
    if "ORCA TERMINATED NORMALLY" not in output_text:
        raise VisualizationError("output is not a normally completed ORCA calculation")
    channels = parse_orbitals(output_text)
    requests = resolve_orbitals(channels, [item.strip() for item in args.orbitals.split(",") if item.strip()], args.spin, args.all_spins)
    pca = pca_axes(parse_xyz(xyz))
    views = [item.strip() for item in args.views.split(",") if item.strip()]
    if set(views) - {"front", "side"}: raise VisualizationError("views must be front and/or side")
    axes = {"front": axis_from_name(args.front_axis, pca), "side": axis_from_name(args.side_axis, pca)}
    reference = pca["largest"]
    matrices = {view: camera_matrix(axes[view], reference) for view in views}
    resolution = PROFILE_RESOLUTIONS[args.profile]
    manifest_path = Path(args.directory).resolve() / "visualization_manifest.json" if args.directory else out.parent / "visualization" / "visualization_manifest.json"
    comparison = comparison_check(Path(args.comparison_manifest).resolve() if args.comparison_manifest else None, args.isovalue, args.profile, views, args.allow_comparison_exception)
    return {"manifest_path": manifest_path, "out": out, "gbw": gbw, "xyz": xyz, "input": input_path, "output_text": output_text, "requests": requests, "pca": pca, "axes": axes, "matrices": matrices, "views": views, "resolution": resolution, "comparison": comparison}


def execute(args: argparse.Namespace) -> Path:
    plan = build_plan(args); directory = plan["manifest_path"].parent; directory.mkdir(parents=True, exist_ok=True)
    template_path = Path(__file__).resolve().parents[1] / "templates" / "vmd" / "orbital_render.tcl"
    template = template_path.read_text(encoding="utf-8")
    records, render_results = [], []
    for requested in plan["requests"]:
        cube = directory / f"{requested.label}.cube"
        cube_result = {"status": "PLANNED", "path": str(cube)}
        if args.execute:
            try:
                cube_result = {"status": "GENERATED", **generate_cube(plan["gbw"], requested.orbital.index, requested.operator, cube, args.grid, args.orca_plot)}
            except OrcaPlotError as exc:
                cube_result = {"status": "CUBE_FAILED", "error": str(exc), "path": str(cube)}
        records.append({"label": requested.label, "index": requested.orbital.index, "spin": requested.orbital.spin, "operator": requested.operator, "occupation": requested.orbital.occupation, "energy_hartree": requested.orbital.energy_hartree, "energy_ev": requested.orbital.energy_ev, "cube": cube_result})
        for view in plan["views"]:
            tga, png = directory / f"{requested.label}_{view}.tga", directory / f"{requested.label}_{view}.png"
            script = directory / f"render_{requested.label}_{view}.tcl"
            script.write_text(tcl_text(template, plan["xyz"], cube, tga, args.isovalue, plan["matrices"][view], plan["resolution"]), encoding="utf-8")
            result = {"label": requested.label, "view": view, "script": str(script), "tga": str(tga), "png": str(png), "status": "PLANNED"}
            if args.execute and cube_result["status"] == "GENERATED" and args.renderer == "vmd": result.update(run_vmd(script, tga, png, args.vmd))
            elif args.execute and cube_result["status"] == "GENERATED" and args.renderer == "none": result["status"] = "CUBE_ONLY"
            render_results.append(result)
    metadata = input_metadata(plan["input"])
    sources = {"output": source_record(plan["out"]), "gbw": source_record(plan["gbw"]), "xyz": source_record(plan["xyz"]), "input": source_record(plan["input"])}
    calculation_hash = hashlib.sha256("".join(value["sha256"] for value in sources.values() if value).encode()).hexdigest()
    manifest = {"schema_version": 1, "tool": "AutoORCA orbital_visualize.py", "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "execution_mode": "executed" if args.execute else "planned", "source": {**sources, "calculation_sha256": calculation_hash, "orca_version": output_version(plan["output_text"]), "method_metadata": metadata}, "orbitals": records, "cube": {"generator": "orca_plot", "grid": args.grid}, "render": {"renderer": "VMD/Tachyon" if args.renderer == "vmd" else "none", "profile": args.profile, "resolution": list(plan["resolution"]), "isovalue": args.isovalue, "projection": "orthographic", "camera_convention": "PCA-or-explicit-axis-v1", "views": plan["views"], "view_axes": plan["axes"], "camera_matrices": plan["matrices"], "results": render_results}, "comparison": plan["comparison"], "limitations": ["No ORCA input was modified and no electronic-structure calculation was launched.", "MO images alone do not establish ICT.", "An overall MO phase inversion has no physical significance."]}
    plan["manifest_path"].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = ["# AutoORCA orbital visualization", "", f"Mode: `{manifest['execution_mode']}`", f"Manifest: `{plan['manifest_path'].name}`", "", "## Orbitals", ""]
    summary += [f"- {record['label']}: ORCA MO {record['index']} ({record['spin']}), {record['energy_ev']} eV; cube {record['cube']['status']}" for record in records]
    summary += ["", "This visualization is a post-processing artifact, not independent evidence of ICT or a replacement for state/NTO analysis.", ""]
    (directory / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    return plan["manifest_path"]


def arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or create reproducible ORCA MO visualization artifacts.")
    parser.add_argument("--gbw", required=True); parser.add_argument("--output", required=True); parser.add_argument("--xyz", required=True); parser.add_argument("--input")
    parser.add_argument("--orbitals", default="HOMO,LUMO"); parser.add_argument("--spin", choices=("alpha", "beta")); parser.add_argument("--all-spins", action="store_true")
    parser.add_argument("--views", default="front,side"); parser.add_argument("--front-axis", choices=("smallest", "middle", "largest", "x", "y", "z"), default="smallest"); parser.add_argument("--side-axis", choices=("smallest", "middle", "largest", "x", "y", "z"), default="middle")
    parser.add_argument("--isovalue", type=float, default=0.03); parser.add_argument("--profile", choices=PROFILE_RESOLUTIONS, default="publication"); parser.add_argument("--grid", type=int, default=100); parser.add_argument("--directory")
    parser.add_argument("--renderer", choices=("vmd", "none"), default="vmd"); parser.add_argument("--orca-plot"); parser.add_argument("--vmd"); parser.add_argument("--execute", action="store_true")
    parser.add_argument("--comparison-manifest"); parser.add_argument("--allow-comparison-exception", action="store_true")
    return parser


def main() -> None:
    args = arguments().parse_args()
    if args.isovalue <= 0: raise SystemExit("--isovalue must be positive")
    try:
        manifest = execute(args)
    except (OSError, json.JSONDecodeError, VisualizationError) as exc:
        print(f"[ORBITAL-VISUALIZATION] ERROR: {exc}", file=sys.stderr); raise SystemExit(2)
    print(f"[ORBITAL-VISUALIZATION] Manifest written: {manifest}")


if __name__ == "__main__": main()
