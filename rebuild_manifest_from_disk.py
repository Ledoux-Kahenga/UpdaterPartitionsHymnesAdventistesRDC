#!/usr/bin/env python3
"""Reconstruit manifest.json depuis les PDF déjà présents sur disque."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[0]
DB = ROOT / "assets" / "HymnesAdventistesDataBase_20261015_170602.db"
SRC_SDAH = ROOT / "assets" / "Partitions_" / "Partitions_SDA_Hymnal_pro_sfwhymnal"

RE_SDAH_SIMPLE = re.compile(r"^score(\d{3})\.pdf$", re.I)
RE_SDAH_LINKED = re.compile(r"^score(\d{3})(m)?_(.+)\.pdf$", re.I)
RE_NZK = re.compile(r"^NyimboZaKristo-(\d+)([A-Za-z]*)\.pdf$", re.I)
RE_HL = re.compile(r"^H(\d{3})([A-Za-z0-9_-]*)\.pdf$", re.I)
RE_DLG = re.compile(r"^D(\d{3})([A-Za-z0-9_-]*)\.pdf$", re.I)
RE_CH = re.compile(r"^(\d+)\.pdf$", re.I)


def page_count(path: Path) -> int:
    if PdfReader is None:
        return 1
    try:
        return max(1, len(PdfReader(str(path)).pages))
    except Exception:
        return 1


def hymn_numbers(table: str) -> list[int]:
    con = sqlite3.connect(DB)
    cols = [r[1] for r in con.execute(f"PRAGMA table_info([{table}])")]
    num_col = "numberLyric" if "numberLyric" in cols else "number"
    rows = con.execute(
        f"SELECT [{num_col}] FROM [{table}] ORDER BY CAST([{num_col}] AS INTEGER)"
    ).fetchall()
    return [int(r[0]) for r in rows if str(r[0]).isdigit()]


def normalize_linked(primary: int, raw: str) -> int | None:
    if not raw.isdigit():
        return None
    n = int(raw)
    if len(raw) >= 3:
        return n
    return (primary // 100) * 100 + n


def sdah_nums(name: str) -> list[int]:
    m = RE_SDAH_SIMPLE.match(name)
    if m:
        return [int(m.group(1))]
    m = RE_SDAH_LINKED.match(name)
    if not m:
        return []
    primary = int(m.group(1))
    nums = [primary]
    for part in m.group(3).split("_"):
        linked = normalize_linked(primary, part)
        if linked is not None and linked not in nums:
            nums.append(linked)
    return nums


def pages_for_hymn(hymn: int, hymn_nums: list[int], pc: int) -> tuple[int, int]:
    ordered = sorted(hymn_nums)
    if hymn not in ordered or pc <= 1:
        return (1, 1 if pc <= 1 else pc)
    n = len(ordered)
    idx = ordered.index(hymn)
    if pc == n:
        p = idx + 1
        return (p, p)
    if n == 1:
        return (1, pc)
    page = 1 + round(idx * (pc - 1) / (n - 1))
    page = max(1, min(pc, int(page)))
    return (page, page)


def build_sdah(folder: Path) -> dict[int, list[dict]]:
    file_meta: dict[str, tuple[list[int], int]] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        nums = sdah_nums(pdf.name)
        if nums:
            file_meta[pdf.name] = (nums, page_count(pdf))
    index: dict[int, list[dict]] = {}
    for file_name, (nums, pc) in file_meta.items():
        for hymn in nums:
            start, end = pages_for_hymn(hymn, nums, pc)
            entry = {
                "label": "Partition",
                "file": file_name,
                "startPage": start,
                "endPage": end,
            }
            index.setdefault(hymn, [])
            if not any(
                e["file"] == file_name and e["startPage"] == start for e in index[hymn]
            ):
                index[hymn].append(entry)
    for hymn, entries in index.items():
        if len(entries) > 1:
            for i, e in enumerate(entries, start=1):
                e["label"] = f"Partition {i}"
    return index


def build_nzk(folder: Path) -> dict[int, list[dict]]:
    index: dict[int, list[dict]] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        m = RE_NZK.match(pdf.name)
        if not m:
            continue
        hymn = int(m.group(1))
        suffix = m.group(2) or ""
        pc = page_count(pdf)
        entry = {
            "label": f"Partition ({suffix})" if suffix else "Partition",
            "file": pdf.name,
            "startPage": 1,
            "endPage": pc,
        }
        index.setdefault(hymn, []).append(entry)
    return index


def build_prefix(folder: Path, pattern: re.Pattern[str]) -> dict[int, list[dict]]:
    """HL / DLG : H001.pdf + H001s.pdf → liste ordonnée."""
    by_hymn: dict[int, list[tuple[str, Path]]] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        m = pattern.match(pdf.name)
        if not m:
            continue
        hymn = int(m.group(1))
        by_hymn.setdefault(hymn, []).append((pdf.name, pdf))

    index: dict[int, list[dict]] = {}
    for hymn, items in by_hymn.items():
        # Tri : principal (suffixe vide) d'abord, puis variantes
        def sort_key(item: tuple[str, Path]) -> tuple[int, str, str]:
            name = item[0]
            m = pattern.match(name)
            suffix = (m.group(2) if m else "") or ""
            return (0 if suffix == "" else 1, suffix, name)

        items_sorted = sorted(items, key=sort_key)
        entries = []
        for i, (name, path) in enumerate(items_sorted, start=1):
            pc = page_count(path)
            label = "Partition" if len(items_sorted) == 1 else f"Partition {i}"
            entries.append(
                {
                    "label": label,
                    "file": name,
                    "startPage": 1,
                    "endPage": pc,
                }
            )
        index[hymn] = entries
    return index


def build_ch(folder: Path) -> dict[int, list[dict]]:
    index: dict[int, list[dict]] = {}
    for pdf in sorted(folder.glob("*.pdf"), key=lambda p: int(RE_CH.match(p.name).group(1)) if RE_CH.match(p.name) else 0):
        m = RE_CH.match(pdf.name)
        if not m:
            continue
        hymn = int(m.group(1))
        pc = page_count(pdf)
        index[hymn] = [
            {
                "label": "Partition",
                "file": pdf.name,
                "startPage": 1,
                "endPage": pc,
            }
        ]
    return index


def block(folder: str, index: dict[int, list[dict]]) -> dict:
    return {
        "folder": folder,
        "count": len(index),
        "hymns": {
            str(n): entries for n, entries in sorted(index.items())
        },
    }


def main() -> None:
    sdah_src = OUT / "sdah"
    if not sdah_src.is_dir() or not any(sdah_src.glob("*.pdf")):
        sdah_src = SRC_SDAH

    sdah = build_sdah(sdah_src)
    nzk = build_nzk(OUT / "nzk")
    hl = build_prefix(OUT / "hl", RE_HL)
    dlg = build_prefix(OUT / "dlg", RE_DLG)
    ch = build_ch(OUT / "ch")

    # Couverture DB
    for label, table, index in (
        ("HL", "HLTb", hl),
        ("DLG", "DLGTb", dlg),
        ("CH", "CHTb", ch),
    ):
        nums = hymn_numbers(table)
        miss = [n for n in nums if n not in index]
        print(f"{label}: disk={len(index)} DB={len(nums)} miss={miss}")

    assert hl[13][0]["file"].startswith("H013")
    assert 14 in sdah and sdah[14][0]["startPage"] == 2

    # version++
    old_v = 2
    vf = OUT / "version.txt"
    if vf.exists():
        try:
            old_v = int(vf.read_text().strip())
        except Exception:
            pass
    version = max(old_v + 1, 3)

    manifest = {
        "version": version,
        "source": "Partitions_ + Trois Anges (HL/DLG) + hymnal.pro (CH)",
        "notes": (
            "startPage/endPage 1-based. "
            "HL/DLG: Partition N = variantes Hnnns.pdf. "
            "CH 703 absent sur hymnal.pro."
        ),
        "hymnals": {
            "SDAH": block("sdah", sdah),
            "NZKristoTb": block("nzk", nzk),
            "HLTb": block("hl", hl),
            "DLGTb": block("dlg", dlg),
            "CHTb": block("ch", ch),
        },
    }

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    vf.write_text(str(version), encoding="utf-8")
    print(f"manifest v{version} written")
    print(
        "counts:",
        {k: v["count"] for k, v in manifest["hymnals"].items()},
    )


if __name__ == "__main__":
    main()
