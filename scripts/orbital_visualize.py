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
BOHR_TO_ANGSTROM = 0.529177210903
ORCA_PLOT_BACKEND_VERSION = "6.1"
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
            if "ORBITALS MANIFOLD" in upper:
                continue
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
    return [item[1] for item in parse_xyz_atoms(path)]


def parse_xyz_atoms(path: Path) -> list[tuple[str, tuple[float, float, float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        count = int(lines[0].strip())
    except (IndexError, ValueError) as exc:
        raise VisualizationError(f"invalid XYZ atom count: {path}") from exc
    points: list[tuple[str, tuple[float, float, float]]] = []
    for line in lines[2:2 + count]:
        fields = line.split()
        if len(fields) < 4:
            raise VisualizationError(f"invalid XYZ coordinate line: {line!r}")
        points.append((fields[0], tuple(float(value) for value in fields[1:4])))
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


def _canonical_sign(axis: tuple[float, float, float]) -> tuple[float, float, float]:
    """Choose an eigenvector sign deterministically (largest component positive)."""
    pivot = max(range(3), key=lambda index: (abs(axis[index]), -index))
    return axis if axis[pivot] >= 0 else tuple(-item for item in axis)


def pca_axes(points: list[tuple[float, float, float]]) -> dict:
    if len(points) < 3:
        raise VisualizationError("at least three XYZ atoms are needed for PCA camera orientation")
    center = tuple(sum(point[i] for point in points) / len(points) for i in range(3))
    cov = [[sum((point[i]-center[i])*(point[j]-center[j]) for point in points) / len(points) for j in range(3)] for i in range(3)]
    eigenvalues, axes = _jacobi_eigensystem(cov)
    # Eigenvector signs are arbitrary. Canonicalize the long and middle axes,
    # then construct the plane normal with a right-handed cross product.
    largest = _canonical_sign(axes[2])
    middle = _canonical_sign(axes[1])
    smallest = _normal(_cross(largest, middle))
    return {"centroid": center, "eigenvalues": eigenvalues, "smallest": smallest, "middle": middle, "largest": largest}


def axis_from_name(name: str, pca: dict) -> tuple[float, float, float]:
    fixed = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
    return fixed[name] if name in fixed else pca[name]


def camera_matrix(view_axis: tuple[float, float, float], reference_axis: tuple[float, float, float]) -> list[float]:
    z_axis = _normal(view_axis)
    x_axis = _cross(reference_axis, z_axis)
    if math.sqrt(sum(x*x for x in x_axis)) < 1.0e-8:
        # Pick the Cartesian reference least parallel to the requested view.
        fallback = min(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), key=lambda axis: abs(sum(a*b for a, b in zip(axis, z_axis))))
        x_axis = _cross(fallback, z_axis)
    x_axis = _normal(x_axis)
    y_axis = _normal(_cross(z_axis, x_axis))
    return [*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, 0.0, 0.0, 0.0, 1.0]


def output_version(text: str) -> str | None:
    match = re.search(r"(?:Program\s+)?Version\s*[:= ]+([^\s,;]+)", text, re.I)
    return match.group(1) if match else None


def require_source_identity(out: Path, gbw: Path, orca_version: str | None) -> dict:
    """Bind the output-derived MO labels to the GBW used by orca_plot."""
    if out.stem != gbw.stem or out.parent != gbw.parent:
        raise VisualizationError("SOURCE_IDENTITY_MISMATCH: output and GBW must have the same basename and directory")
    if not orca_version or not orca_version.startswith(f"{ORCA_PLOT_BACKEND_VERSION}."):
        raise VisualizationError(f"ORCA61_REQUIRED: output reports {orca_version or 'no ORCA version'}, but the automated orca_plot menu targets ORCA {ORCA_PLOT_BACKEND_VERSION}.x")
    return {"out_gbw": "VERIFIED", "identity_rule": "matching basename plus completed ORCA 6.1.x output", "orca_plot_backend_version": ORCA_PLOT_BACKEND_VERSION}


def parse_cube_atoms(path: Path) -> list[tuple[int, tuple[float, float, float]]]:
    """Read Gaussian Cube atom coordinates and normalize them to Angstrom."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 6:
        raise VisualizationError(f"invalid Gaussian Cube (too short): {path}")
    try:
        atom_count = int(lines[2].split()[0])
        grid_counts = [int(lines[index].split()[0]) for index in range(3, 6)]
    except (IndexError, ValueError) as exc:
        raise VisualizationError(f"invalid Gaussian Cube header: {path}") from exc
    count = abs(atom_count)
    atom_lines = lines[6:6 + count]
    if len(atom_lines) != count:
        raise VisualizationError(f"Gaussian Cube declares {count} atoms but is truncated")
    # Conventional positive grid counts use Bohr; negative counts signal Angstrom.
    factor = 1.0 if any(value < 0 for value in grid_counts) else BOHR_TO_ANGSTROM
    atoms = []
    for line in atom_lines:
        fields = line.split()
        if len(fields) < 5:
            raise VisualizationError(f"invalid Gaussian Cube atom line: {line!r}")
        atoms.append((int(float(fields[0])), tuple(float(value) * factor for value in fields[2:5])))
    return atoms


def verify_cube_xyz(cube: Path, xyz: Path, tolerance_angstrom: float = 0.01) -> dict:
    """Require the generated cube to describe the exact ordered XYZ geometry."""
    cube_atoms, xyz_atoms = parse_cube_atoms(cube), parse_xyz_atoms(xyz)
    if len(cube_atoms) != len(xyz_atoms):
        raise VisualizationError(f"CUBE_XYZ_MISMATCH: cube has {len(cube_atoms)} atoms; XYZ has {len(xyz_atoms)}")
    max_deviation = 0.0
    for index, ((_, cube_point), (_, xyz_point)) in enumerate(zip(cube_atoms, xyz_atoms)):
        deviation = math.sqrt(sum((a-b)**2 for a, b in zip(cube_point, xyz_point)))
        max_deviation = max(max_deviation, deviation)
        if deviation > tolerance_angstrom:
            raise VisualizationError(f"CUBE_XYZ_MISMATCH: atom {index} differs by {deviation:.6f} A (limit {tolerance_angstrom:.6f} A)")
    return {"status": "VERIFIED", "coordinate_tolerance_angstrom": tolerance_angstrom, "max_coordinate_deviation_angstrom": max_deviation, "cube_sha256": sha256(cube)}


def input_metadata(path: Path | None) -> dict:
    if not path:
        return {}
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*#\s*@([A-Z_]+):\s*(.*?)\s*$", line, re.I)
        if match:
            data[match.group(1).lower()] = match.group(2)
    return data


def comparison_check(reference: Path | None, isovalue: float, profile: str, views: list[str], selectors: dict[str, str], allow: bool, reason: str | None) -> dict | None:
    if reference is None:
        return None
    other = json.loads(reference.read_text(encoding="utf-8"))
    render = other.get("render", {})
    differences = []
    if float(render.get("isovalue", -1)) != isovalue: differences.append("isovalue")
    if render.get("profile") != profile: differences.append("profile")
    if render.get("views") != views: differences.append("views")
    if render.get("camera_convention") != "PCA-or-explicit-axis-v1": differences.append("camera convention")
    if render.get("view_axis_selectors") != selectors: differences.append("view axis selectors")
    if differences and not allow:
        raise VisualizationError("COMPARISON_CONVENTION_MISMATCH: " + ", ".join(differences))
    if differences and not reason:
        raise VisualizationError("COMPARISON_EXCEPTION_REASON_REQUIRED")
    return {"reference_manifest": str(reference.resolve()), "differences": differences, "exception_approved": bool(differences and allow), "exception_reason": reason if differences else None}


def matrix_tcl(matrix: list[float]) -> str:
    """Serialize a VMD 4x4 matrix as nested Tcl lists, never a flat vector."""
    if len(matrix) != 16:
        raise VisualizationError("camera matrix must contain 16 elements")
    rows = [matrix[index:index + 4] for index in range(0, 16, 4)]
    body = " ".join("{" + " ".join(f"{value:.10g}" for value in row) + "}" for row in rows)
    return "{{" + body + "}}"


def tcl_text(template: str, xyz: Path, cube: Path, tga: Path, isovalue: float, matrix: list[float], resolution: tuple[int, int]) -> str:
    replacements = {
        "{{XYZ}}": str(xyz.resolve()).replace("\\", "/"), "{{CUBE}}": str(cube.resolve()).replace("\\", "/"),
        "{{TGA}}": str(tga.resolve()).replace("\\", "/"), "{{ISOVALUE}}": f"{isovalue:.6g}",
        "{{ROTATE_MATRIX}}": matrix_tcl(matrix),
        "{{WIDTH}}": str(resolution[0]), "{{HEIGHT}}": str(resolution[1]),
    }
    for key, value in replacements.items(): template = template.replace(key, value)
    return template


def executable_version(executable: str, flag: str, timeout_seconds: int = 15) -> str | None:
    try:
        result = subprocess.run([executable, flag], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=timeout_seconds)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = result.stdout.strip().replace("\r", " ").replace("\n", " ")
    return text[:500] or None


def image_converter() -> tuple[str, str | None] | None:
    """Find ImageMagick without mistaking Windows' filesystem ``convert`` for it."""
    for candidate in (shutil.which("magick"), shutil.which("convert")):
        if not candidate:
            continue
        version = executable_version(candidate, "-version")
        if version and "imagemagick" in version.lower():
            return candidate, version
    return None


def run_vmd(script: Path, tga: Path, png: Path, vmd: str | None, timeout_seconds: int) -> dict:
    executable = vmd or shutil.which("vmd")
    if not executable:
        return {"status": "VMD_NOT_AVAILABLE"}
    version = executable_version(executable, "-version")
    try:
        completed = subprocess.run([executable, "-dispdev", "text", "-e", str(script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {"status": "VMD_TIMEOUT", "vmd_version": version, "timeout_seconds": timeout_seconds}
    except OSError as exc:
        return {"status": "VMD_START_FAILED", "vmd_version": version, "error": str(exc)}
    if completed.returncode != 0 or not tga.is_file():
        return {"status": "VMD_FAILED", "vmd_version": version, "stdout_tail": completed.stdout[-2000:]}
    converter_info = image_converter()
    if not converter_info:
        return {"status": "PNG_CONVERTER_NOT_AVAILABLE", "vmd_version": version, "tga": str(tga), "tga_sha256": sha256(tga)}
    converter, converter_version = converter_info
    try:
        converted = subprocess.run([converter, str(tga), str(png)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {"status": "PNG_CONVERSION_TIMEOUT", "vmd_version": version, "png_converter_version": converter_version, "tga": str(tga), "tga_sha256": sha256(tga)}
    except OSError as exc:
        return {"status": "PNG_CONVERSION_START_FAILED", "vmd_version": version, "png_converter_version": converter_version, "error": str(exc), "tga": str(tga), "tga_sha256": sha256(tga)}
    status = "RENDERED" if converted.returncode == 0 and png.is_file() else "PNG_CONVERSION_FAILED"
    result = {"status": status, "vmd_version": version, "png_converter_version": converter_version, "tga": str(tga), "tga_sha256": sha256(tga), "png": str(png)}
    if status == "RENDERED": result["png_sha256"] = sha256(png)
    return result


def build_plan(args: argparse.Namespace) -> dict:
    out, gbw, xyz = Path(args.output).resolve(), Path(args.gbw).resolve(), Path(args.xyz).resolve()
    input_path = Path(args.input).resolve() if args.input else None
    for item in (out, gbw, xyz):
        if not item.is_file(): raise VisualizationError(f"required source does not exist: {item}")
    output_text = out.read_text(encoding="utf-8", errors="replace")
    if "ORCA TERMINATED NORMALLY" not in output_text:
        raise VisualizationError("output is not a normally completed ORCA calculation")
    orca_version = output_version(output_text)
    source_binding = require_source_identity(out, gbw, orca_version)
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
    selectors = {"front": args.front_axis, "side": args.side_axis}
    comparison = comparison_check(Path(args.comparison_manifest).resolve() if args.comparison_manifest else None, args.isovalue, args.profile, views, selectors, args.allow_comparison_exception, args.comparison_exception_reason)
    return {"manifest_path": manifest_path, "out": out, "gbw": gbw, "xyz": xyz, "input": input_path, "output_text": output_text, "orca_version": orca_version, "source_binding": source_binding, "requests": requests, "pca": pca, "axes": axes, "matrices": matrices, "views": views, "selectors": selectors, "resolution": resolution, "comparison": comparison}


def execute(args: argparse.Namespace) -> Path:
    plan = build_plan(args); directory = plan["manifest_path"].parent; directory.mkdir(parents=True, exist_ok=True)
    template_path = Path(__file__).resolve().parents[1] / "templates" / "vmd" / "orbital_render.tcl"
    template = template_path.read_text(encoding="utf-8")
    records, render_results = [], []
    for requested in plan["requests"]:
        cube = directory / f"{requested.label}.cube"
        cube_result = {"status": "PLANNED", "path": str(cube)}
        cube_binding = {"status": "PENDING"}
        if args.execute:
            try:
                cube_result = {"status": "GENERATED", **generate_cube(plan["gbw"], requested.orbital.index, requested.operator, cube, args.grid, args.orca_plot, args.orca_plot_timeout)}
                cube_binding = verify_cube_xyz(cube, plan["xyz"])
                cube_result["sha256"] = cube_binding["cube_sha256"]
            except OrcaPlotError as exc:
                cube_result = {"status": "CUBE_FAILED", "error": str(exc), "path": str(cube)}
            except VisualizationError as exc:
                cube_result = {"status": "CUBE_XYZ_MISMATCH", "error": str(exc), "path": str(cube), "sha256": sha256(cube) if cube.is_file() else None}
                cube_binding = {"status": "MISMATCH", "error": str(exc)}
        records.append({"label": requested.label, "index": requested.orbital.index, "spin": requested.orbital.spin, "operator": requested.operator, "occupation": requested.orbital.occupation, "energy_hartree": requested.orbital.energy_hartree, "energy_ev": requested.orbital.energy_ev, "cube": cube_result, "cube_xyz_binding": cube_binding})
        for view in plan["views"]:
            tga, png = directory / f"{requested.label}_{view}.tga", directory / f"{requested.label}_{view}.png"
            script = directory / f"render_{requested.label}_{view}.tcl"
            script.write_text(tcl_text(template, plan["xyz"], cube, tga, args.isovalue, plan["matrices"][view], plan["resolution"]), encoding="utf-8")
            result = {"label": requested.label, "view": view, "script": str(script), "tga": str(tga), "png": str(png), "status": "PLANNED"}
            if args.execute and cube_result["status"] == "GENERATED" and args.renderer == "vmd": result.update(run_vmd(script, tga, png, args.vmd, args.vmd_timeout))
            elif args.execute and cube_result["status"] == "GENERATED" and args.renderer == "none": result["status"] = "CUBE_ONLY"
            render_results.append(result)
    metadata = input_metadata(plan["input"])
    sources = {"output": source_record(plan["out"]), "gbw": source_record(plan["gbw"]), "xyz": source_record(plan["xyz"]), "input": source_record(plan["input"])}
    calculation_hash = hashlib.sha256("".join(value["sha256"] for value in sources.values() if value).encode()).hexdigest()
    source_binding = {**plan["source_binding"], "cube_xyz": {record["label"]: record["cube_xyz_binding"] for record in records}}
    manifest = {"schema_version": 2, "tool": "AutoORCA orbital_visualize.py", "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "execution_mode": "executed" if args.execute else "planned", "source": {**sources, "calculation_sha256": calculation_hash, "orca_version": plan["orca_version"], "method_metadata": metadata}, "source_binding": source_binding, "orbitals": records, "cube": {"generator": "orca_plot", "orca_plot_backend_version": ORCA_PLOT_BACKEND_VERSION, "grid": args.grid, "timeout_seconds": args.orca_plot_timeout}, "render": {"renderer": "VMD/Tachyon" if args.renderer == "vmd" else "none", "profile": args.profile, "resolution": list(plan["resolution"]), "isovalue": args.isovalue, "projection": "orthographic", "camera_convention": "PCA-or-explicit-axis-v1", "view_axis_selectors": plan["selectors"], "views": plan["views"], "view_axes": plan["axes"], "camera_matrices": plan["matrices"], "timeout_seconds": args.vmd_timeout, "results": render_results}, "comparison": plan["comparison"], "limitations": ["No ORCA input was modified and no electronic-structure calculation was launched.", "MO images alone do not establish ICT.", "An overall MO phase inversion has no physical significance."]}
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
    parser.add_argument("--renderer", choices=("vmd", "none"), default="vmd"); parser.add_argument("--orca-plot"); parser.add_argument("--vmd"); parser.add_argument("--orca-plot-timeout", type=int, default=600); parser.add_argument("--vmd-timeout", type=int, default=600); parser.add_argument("--execute", action="store_true")
    parser.add_argument("--comparison-manifest"); parser.add_argument("--allow-comparison-exception", action="store_true"); parser.add_argument("--comparison-exception-reason")
    return parser


def main() -> None:
    args = arguments().parse_args()
    if args.isovalue <= 0 or args.orca_plot_timeout <= 0 or args.vmd_timeout <= 0: raise SystemExit("isovalue and timeouts must be positive")
    try:
        manifest = execute(args)
    except (OSError, json.JSONDecodeError, VisualizationError) as exc:
        print(f"[ORBITAL-VISUALIZATION] ERROR: {exc}", file=sys.stderr); raise SystemExit(2)
    print(f"[ORBITAL-VISUALIZATION] Manifest written: {manifest}")


if __name__ == "__main__": main()
