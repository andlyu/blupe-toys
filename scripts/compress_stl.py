#!/usr/bin/env python3
"""Shrink an STL by decimating each body's mesh (quadric simplification).

CAD exporters often tessellate curves far finer than a 3D printer can
reproduce; this walks every separate body in the file, reduces its triangle
count, and writes a binary STL. Bodies that are already coarse (screws, pins)
are left untouched so small features never collapse.

    python3 scripts/compress_stl.py toys/press-button/stl/button.stl
    python3 scripts/compress_stl.py --ratio 0.5 --out small.stl big.stl

Requires: trimesh, fast-simplification (pip install trimesh fast-simplification)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fast_simplification
import trimesh

# Bodies below this triangle count are already coarse; decimating them risks
# destroying small features (screw threads, pins) for negligible savings.
MIN_TRIANGLES = 5_000


def compress(path: Path, out: Path, ratio: float) -> None:
    before = path.stat().st_size
    mesh = trimesh.load_mesh(path)
    bodies = mesh.split(only_watertight=False)
    if len(bodies) == 0:
        bodies = [mesh]

    slimmed = []
    for body in bodies:
        if len(body.faces) < MIN_TRIANGLES:
            slimmed.append(body)
            continue
        verts, faces = fast_simplification.simplify(
            body.vertices, body.faces, target_reduction=ratio
        )
        slimmed.append(trimesh.Trimesh(vertices=verts, faces=faces))

    result = trimesh.util.concatenate(slimmed)
    result.export(out)

    after = out.stat().st_size
    print(
        f"{path.name}: {len(mesh.faces):,} -> {len(result.faces):,} triangles, "
        f"{before / 1e6:.1f} MB -> {after / 1e6:.1f} MB"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stl", nargs="+", type=Path, help="STL file(s) to compress")
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.75,
        help="fraction of triangles to remove from dense bodies (default 0.75)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output path (single input only; default: compress in place)",
    )
    args = parser.parse_args()
    if args.out is not None and len(args.stl) > 1:
        parser.error("--out only works with a single input file")

    for path in args.stl:
        compress(path, args.out or path, args.ratio)


if __name__ == "__main__":
    main()
