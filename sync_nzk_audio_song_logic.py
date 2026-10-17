#!/usr/bin/env python3
"""Remplace le catalogue Drive par les 200 MP3 Song Logic.

1. Copie shap_pro_users_mp3 → remote_partitions/nzk_audio/ (noms NNN.mp3)
2. Génère audios_links.json (URLs GitHub raw)
3. Met à jour assets/data.zip
4. Corrige NZKristoTb.json : 37/66/146 → stems natifs (plus d'emprunts MIDI)
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
SL = (
    ROOT
    / "assets"
    / "Partitions_Nymbo_Za_Kristo_nzkmutz"
    / "raw_files"
    / "shap_pro_users_mp3"
)
AUDIO_DIR = OUT / "nzk_audio"
DATA_ZIP = ROOT / "assets" / "data.zip"
NZK_JSON = ROOT / "assets" / "NZKristoTb.json"

BASE_URL = (
    "https://raw.githubusercontent.com/Ledoux-Kahenga/"
    "UpdaterPartitionsHymnesAdventistesRDC/main/nzk_audio/"
)

VARIANT_TO_NUM = {
    "006b": 6,
    "037a": 37,
    "066(a)": 66,
    "066a": 66,
    "146(b)": 146,
    "146b": 146,
}
IGNORE = {
    "006",
    "037b",
    "066(b)",
    "066b",
    "146(a)",
    "146a",
    "026a",
    "131a",
}


def stem_to_num(stem: str) -> int | None:
    if stem in IGNORE:
        return None
    if stem in VARIANT_TO_NUM:
        return VARIANT_TO_NUM[stem]
    m = re.fullmatch(r"(\d{1,3})", stem)
    return int(m.group(1)) if m else None


def prepare_audio_files() -> dict[int, str]:
    if AUDIO_DIR.exists():
        shutil.rmtree(AUDIO_DIR)
    AUDIO_DIR.mkdir(parents=True)

    mapping: dict[int, str] = {}
    for src in sorted(SL.glob("*.mp3")):
        num = stem_to_num(src.stem)
        if num is None:
            print(f"  skip {src.name}")
            continue
        name = f"{num:03d}.mp3"
        shutil.copy2(src, AUDIO_DIR / name)
        mapping[num] = name
        print(f"  {src.name} -> {name}")
    return mapping


def write_audios_links(mapping: dict[int, str]) -> Path:
    links = {
        mapping[n]: f"{BASE_URL}{mapping[n]}"
        for n in sorted(mapping)
    }
    out_json = OUT / "audios_links.json"
    out_json.write_text(
        json.dumps(links, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Copie aussi à la racine assets pour sécurité / outils
    (ROOT / "assets" / "audios_links.json").write_text(
        json.dumps(links, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"audios_links.json : {len(links)} entrees")
    return out_json


def update_data_zip(links_path: Path) -> None:
    tmp = DATA_ZIP.with_suffix(".zip.tmp")
    with zipfile.ZipFile(DATA_ZIP, "r") as zin, zipfile.ZipFile(
        tmp, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        replaced = False
        for info in zin.infolist():
            name = info.filename
            if name.endswith("audios_links.json") or name == "audios_links.json":
                data = links_path.read_bytes()
                zout.writestr(name, data)
                replaced = True
                print(f"  replaced in zip: {name}")
            else:
                zout.writestr(info, zin.read(info.filename))
        if not replaced:
            zout.writestr("audios_links.json", links_path.read_bytes())
            print("  added audios_links.json to zip root")
    tmp.replace(DATA_ZIP)
    print(f"data.zip updated ({DATA_ZIP.stat().st_size} bytes)")


def fix_nzk_json() -> None:
    hymns = json.loads(NZK_JSON.read_text(encoding="utf-8"))
    changed = []
    for h in hymns:
        n = int(h["nzk_Number"])
        if n in (37, 66, 146):
            old = h.get("nzk_Audio")
            h["nzk_Audio"] = str(n)
            h["nzk_Has_Audio"] = 1
            changed.append((n, old, h["nzk_Audio"]))
        # Si stem numérique et fichier présent dans mapping 1-200 → flag 1
        # (ne touche pas 201-220 qui restent emprunts éventuels)
    NZK_JSON.write_text(
        json.dumps(hymns, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    print("NZKristoTb.json fixes:", changed)


def main() -> None:
    print("=== Copie MP3 Song Logic ===")
    mapping = prepare_audio_files()
    print(f"total: {len(mapping)}")
    assert 6 in mapping and 37 in mapping and 66 in mapping and 146 in mapping
    assert len(mapping) == 200

    print("=== audios_links.json ===")
    links = write_audios_links(mapping)

    print("=== data.zip ===")
    update_data_zip(links)

    print("=== NZKristoTb.json ===")
    fix_nzk_json()

    print("OK — pousser remote_partitions/nzk_audio/ sur GitHub")


if __name__ == "__main__":
    main()
