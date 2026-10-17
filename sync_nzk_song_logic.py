#!/usr/bin/env python3
"""Remplace remote_partitions/nzk par les PDF Song Logic (phone + tablet).

- Source : assets/Partitions_Nymbo_Za_Kristo_nzkmutz/raw_files/
- Variantes choisies → nom canonique NNN.pdf :
    006b → 006, 037a → 037, 066(a) → 066, 146(b) → 146
- phone_mode (+ public pour trous / 006)
- tablet_mode (+ public) ; si absent → copie phone
- Supprime les anciens NyimboZaKristo-*.pdf
- Met à jour manifest.json (NZKristoTb)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
SRC = ROOT / "assets" / "Partitions_Nymbo_Za_Kristo_nzkmutz" / "raw_files"
NZK_ROOT = OUT / "nzk"
PHONE = NZK_ROOT / "phone"
TABLET = NZK_ROOT / "tablet"

# stem Song Logic → numéro logique app (1..220)
VARIANT_TO_NUM = {
    "006b": 6,
    "037a": 37,
    "066(a)": 66,
    "066a": 66,
    "146(b)": 146,
    "146b": 146,
}

# stems à ignorer (non choisis)
IGNORE_STEMS = {
    "006",
    "026a",
    "037b",
    "066(b)",
    "066b",
    "131a",
    "146(a)",
    "146a",
}


def stem_to_number(stem: str) -> int | None:
    if stem in IGNORE_STEMS:
        return None
    if stem in VARIANT_TO_NUM:
        return VARIANT_TO_NUM[stem]
    # 001, 026, 131…
    m = re.fullmatch(r"(\d{1,3})", stem)
    if m:
        return int(m.group(1))
    # 066(a) already handled
    m = re.fullmatch(r"(\d{1,3})\([ab]\)", stem, re.I)
    if m:
        return None  # non listé = ignorer
    m = re.fullmatch(r"(\d{1,3})[ab]", stem, re.I)
    if m:
        return None
    return None


def collect_mode(primary: Path, public: Path) -> dict[int, Path]:
    """num → path source (primary écrase public)."""
    out: dict[int, Path] = {}
    for folder in (public, primary):
        if not folder.is_dir():
            continue
        for pdf in folder.glob("*.pdf"):
            num = stem_to_number(pdf.stem)
            if num is None or num < 1 or num > 220:
                continue
            out[num] = pdf
    return out


def copy_as_canonical(src: Path, dest_dir: Path, num: int) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{num:03d}.pdf"
    dest = dest_dir / name
    shutil.copy2(src, dest)
    return name


def rebuild_manifest_nzk(phone_files: dict[int, str], tablet_files: dict[int, str]) -> None:
    path = OUT / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
    else:
        manifest = {"version": 1, "hymnals": {}}

    version = int(manifest.get("version") or 1) + 1
    manifest["version"] = version
    notes = str(manifest.get("notes") or "")
    if "Song Logic" not in notes:
        manifest["notes"] = (
            notes + " NZK: Song Logic phone/tablet (shortestSide>=600 → tablet)."
        ).strip()

    hymns: dict[str, list[dict]] = {}
    for num in sorted(set(phone_files) | set(tablet_files)):
        entries = []
        if num in phone_files:
            entries.append(
                {
                    "label": "Partition",
                    "file": phone_files[num],
                    "mode": "phone",
                    "startPage": 1,
                    "endPage": 1,
                }
            )
        if num in tablet_files:
            entries.append(
                {
                    "label": "Partition",
                    "file": tablet_files[num],
                    "mode": "tablet",
                    "startPage": 1,
                    "endPage": 1,
                }
            )
        hymns[str(num)] = entries

    manifest.setdefault("hymnals", {})["NZKristoTb"] = {
        "folder": "nzk",
        "folderPhone": "nzk/phone",
        "folderTablet": "nzk/tablet",
        "count": len(hymns),
        "source": "Song Logic nzkmutz (phone_mode / tablet_mode)",
        "hymns": hymns,
    }

    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "version.txt").write_text(str(version), encoding="utf-8")
    print(f"manifest v{version} NZK={len(hymns)}")


def main() -> None:
    phone_src = collect_mode(SRC / "phone_mode", SRC / "phone_mode_public")
    tablet_src = collect_mode(SRC / "tablet_mode", SRC / "tablet_mode_public")

    print(f"phone sources: {len(phone_src)}")
    print(f"tablet sources (raw): {len(tablet_src)}")

    # Purge ancien nzk plat + sous-dossiers
    if NZK_ROOT.exists():
        shutil.rmtree(NZK_ROOT)
    PHONE.mkdir(parents=True)
    TABLET.mkdir(parents=True)

    phone_files: dict[int, str] = {}
    for num, src in sorted(phone_src.items()):
        phone_files[num] = copy_as_canonical(src, PHONE, num)

    tablet_files: dict[int, str] = {}
    for num in sorted(set(phone_src) | set(tablet_src)):
        src = tablet_src.get(num) or phone_src.get(num)
        if src is None:
            continue
        tablet_files[num] = copy_as_canonical(src, TABLET, num)

    # Trous phone → reprise tablette (ex. 123, 139, 140)
    for num, name in list(tablet_files.items()):
        if num not in phone_files:
            src = TABLET / name
            phone_files[num] = copy_as_canonical(src, PHONE, num)
            print(f"  phone fallback from tablet: {num:03d}")

    print(f"written phone: {len(phone_files)} tablet: {len(tablet_files)}")
    miss_phone = [n for n in range(1, 221) if n not in phone_files]
    miss_tab = [n for n in range(1, 221) if n not in tablet_files]
    print(f"missing phone (1-220): {miss_phone}")
    print(f"missing tablet (1-220): {miss_tab}")
    for n in (6, 26, 37, 66, 131, 146):
        print(
            f"  #{n}: phone={phone_files.get(n)} tablet={tablet_files.get(n)}"
        )

    rebuild_manifest_nzk(phone_files, tablet_files)


if __name__ == "__main__":
    main()
