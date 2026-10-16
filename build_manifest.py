#!/usr/bin/env python3
"""Génère manifest.json + optionnellement copie les PDF pour publication GitHub."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_SDAH = ROOT / "assets" / "Partitions_" / "Partitions_SDA_Hymnal_pro_sfwhymnal"
SRC_NZK = ROOT / "assets" / "Partitions_" / "Partitions_Nyimbo_Za_Kristo_nzkhymnal"
OUT = Path(__file__).resolve().parent

RE_SDAH_SIMPLE = re.compile(r"^score(\d{3})\.pdf$", re.I)
RE_SDAH_MULTI = re.compile(r"^score(\d{3})m_(.+)\.pdf$", re.I)
RE_NZK = re.compile(r"^NyimboZaKristo-(\d+)([A-Za-z]*)\.pdf$", re.I)


def sdah_numbers(name: str) -> list[int]:
    m = RE_SDAH_SIMPLE.match(name)
    if m:
        return [int(m.group(1))]
    m = RE_SDAH_MULTI.match(name)
    if m:
        nums = [int(m.group(1))]
        for part in m.group(2).split("_"):
            if part.isdigit():
                nums.append(int(part))
        return nums
    m = re.search(r"score(\d+)", name, re.I)
    return [int(m.group(1))] if m else []


def build_index(
    folder: Path, number_fn
) -> dict[int, list[str]]:
    index: dict[int, list[str]] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        for n in number_fn(pdf.name):
            index.setdefault(n, [])
            if pdf.name not in index[n]:
                index[n].append(pdf.name)
    return index


def parts_for(files: list[str], recueil: str) -> list[dict]:
    files = sorted(files)
    out = []
    for i, fn in enumerate(files, start=1):
        if len(files) == 1:
            label = "Partition"
        elif recueil == "NZKristoTb":
            m = RE_NZK.match(fn)
            suffix = m.group(2) if m else ""
            label = f"Partition ({suffix})" if suffix else f"Partition {i}"
        else:
            label = f"Partition {i}"
        out.append({"label": label, "file": fn})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copie les PDF vers remote_partitions/sdah et nzk (pour push GitHub)",
    )
    args = parser.parse_args()

    if not SRC_SDAH.is_dir() or not SRC_NZK.is_dir():
        raise SystemExit(f"Dossiers source introuvables:\n  {SRC_SDAH}\n  {SRC_NZK}")

    sdah = build_index(SRC_SDAH, sdah_numbers)
    nzk = build_index(SRC_NZK, lambda n: [int(m.group(1))] if (m := RE_NZK.match(n)) else [])

    manifest = {
        "version": 1,
        "source": "Partitions_ (sfwhymnal / nzkhymnal)",
        "hymnals": {
            "SDAH": {
                "folder": "sdah",
                "count": len(sdah),
                "hymns": {
                    str(n): parts_for(files, "SDAH")
                    for n, files in sorted(sdah.items())
                },
            },
            "NZKristoTb": {
                "folder": "nzk",
                "count": len(nzk),
                "hymns": {
                    str(n): parts_for(files, "NZKristoTb")
                    for n, files in sorted(nzk.items())
                },
            },
        },
    }

    out_manifest = OUT / "manifest.json"
    out_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "version.txt").write_text(str(manifest["version"]), encoding="utf-8")

    print(f"SDAH : {len(sdah)} chants -> {out_manifest}")
    print(f"NZK  : {len(nzk)} chants")

    if args.copy:
        for folder_name, src, index in (
            ("sdah", SRC_SDAH, sdah),
            ("nzk", SRC_NZK, nzk),
        ):
            dest = OUT / folder_name
            dest.mkdir(parents=True, exist_ok=True)
            names = {fn for files in index.values() for fn in files}
            copied = 0
            for name in sorted(names):
                target = dest / name
                if target.exists() and target.stat().st_size > 0:
                    continue
                shutil.copy2(src / name, target)
                copied += 1
            print(f"Copied {copied} PDF -> {dest} (indexed: {len(names)})")


if __name__ == "__main__":
    main()
