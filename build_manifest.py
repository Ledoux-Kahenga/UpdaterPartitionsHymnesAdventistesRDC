#!/usr/bin/env python3
"""Génère manifest.json + optionnellement copie les PDF pour publication GitHub.

Pour SDAH, les fichiers du type score013m_014.pdf couvrent plusieurs n° :
chaque chant reçoit startPage/endPage pour n'afficher que sa/ses page(s).
"""

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
RE_SDAH_LINKED = re.compile(r"^score(\d{3})(m)?_(.+)\.pdf$", re.I)
RE_NZK = re.compile(r"^NyimboZaKristo-(\d+)([A-Za-z]*)\.pdf$", re.I)

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore


def _normalize_linked_number(primary: int, raw: str) -> int | None:
    if not raw.isdigit():
        return None
    n = int(raw)
    if len(raw) >= 3:
        return n
    return (primary // 100) * 100 + n


def sdah_numbers(name: str) -> list[int]:
    m = RE_SDAH_SIMPLE.match(name)
    if m:
        return [int(m.group(1))]
    m = RE_SDAH_LINKED.match(name)
    if m:
        primary = int(m.group(1))
        nums = [primary]
        for part in m.group(3).split("_"):
            linked = _normalize_linked_number(primary, part)
            if linked is not None and linked not in nums:
                nums.append(linked)
        return nums
    m = re.search(r"score(\d+)", name, re.I)
    return [int(m.group(1))] if m else []


def pdf_page_count(path: Path) -> int:
    if PdfReader is None:
        return 1
    try:
        return max(1, len(PdfReader(str(path)).pages))
    except Exception:
        return 1


def pages_for_hymn(hymn: int, hymn_nums: list[int], page_count: int) -> tuple[int, int]:
    """Retourne (startPage, endPage) 1-based pour un chant dans un PDF partagé."""
    ordered = sorted(hymn_nums)
    if hymn not in ordered:
        return (1, page_count)

    if page_count <= 1:
        return (1, 1)

    n = len(ordered)
    idx = ordered.index(hymn)

    # Cas idéal : une page PDF par numéro (ex. 013m_014 → 2 pages)
    if page_count == n:
        p = idx + 1
        return (p, p)

    # Sinon : projection linéaire sur les pages disponibles
    if n == 1:
        return (1, page_count)
    page = 1 + round(idx * (page_count - 1) / (n - 1))
    page = max(1, min(page_count, int(page)))
    return (page, page)


def build_sdah_index(folder: Path) -> dict[int, list[dict]]:
    """number -> [{label, file, startPage, endPage}, ...]"""
    # file -> (nums, page_count)
    file_meta: dict[str, tuple[list[int], int]] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        nums = sdah_numbers(pdf.name)
        if not nums:
            continue
        file_meta[pdf.name] = (nums, pdf_page_count(pdf))

    index: dict[int, list[dict]] = {}
    for file_name, (nums, page_count) in file_meta.items():
        for hymn in nums:
            start, end = pages_for_hymn(hymn, nums, page_count)
            entry = {
                "label": "Partition",
                "file": file_name,
                "startPage": start,
                "endPage": end,
            }
            index.setdefault(hymn, [])
            # Évite les doublons exacts
            if not any(
                e["file"] == file_name
                and e["startPage"] == start
                and e["endPage"] == end
                for e in index[hymn]
            ):
                index[hymn].append(entry)

    # Labels si plusieurs parties
    for hymn, entries in index.items():
        if len(entries) == 1:
            continue
        for i, e in enumerate(entries, start=1):
            e["label"] = f"Partition {i}"
    return index


def build_nzk_index(folder: Path) -> dict[int, list[dict]]:
    index: dict[int, list[dict]] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        m = RE_NZK.match(pdf.name)
        if not m:
            continue
        hymn = int(m.group(1))
        suffix = m.group(2) or ""
        pages = pdf_page_count(pdf)
        entry = {
            "label": f"Partition ({suffix})" if suffix else "Partition",
            "file": pdf.name,
            "startPage": 1,
            "endPage": pages,
        }
        index.setdefault(hymn, []).append(entry)

    for hymn, entries in index.items():
        if len(entries) == 1 and entries[0]["label"].startswith("Partition ("):
            # Une seule variante : garder le label suffixé
            continue
        if len(entries) > 1:
            for i, e in enumerate(entries, start=1):
                if not e["label"].startswith("Partition ("):
                    e["label"] = f"Partition {i}"
    return index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args()

    if not SRC_SDAH.is_dir() or not SRC_NZK.is_dir():
        raise SystemExit(f"Dossiers source introuvables:\n  {SRC_SDAH}\n  {SRC_NZK}")

    sdah = build_sdah_index(SRC_SDAH)
    nzk = build_nzk_index(SRC_NZK)

    # Vérifs cohérence 13/14
    assert sdah[13][0]["file"] == "score013m_014.pdf"
    assert sdah[13][0]["startPage"] == 1 and sdah[13][0]["endPage"] == 1
    assert sdah[14][0]["file"] == "score013m_014.pdf"
    assert sdah[14][0]["startPage"] == 2 and sdah[14][0]["endPage"] == 2

    manifest = {
        "version": 2,
        "source": "Partitions_ (sfwhymnal / nzkhymnal)",
        "notes": "startPage/endPage 1-based : pages du PDF à afficher pour ce n°",
        "hymnals": {
            "SDAH": {
                "folder": "sdah",
                "count": len(sdah),
                "hymns": {str(n): entries for n, entries in sorted(sdah.items())},
            },
            "NZKristoTb": {
                "folder": "nzk",
                "count": len(nzk),
                "hymns": {str(n): entries for n, entries in sorted(nzk.items())},
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
    print("Check 13:", sdah[13])
    print("Check 14:", sdah[14])

    if args.copy:
        for folder_name, src, index in (
            ("sdah", SRC_SDAH, sdah),
            ("nzk", SRC_NZK, nzk),
        ):
            dest = OUT / folder_name
            dest.mkdir(parents=True, exist_ok=True)
            names = {e["file"] for entries in index.values() for e in entries}
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
