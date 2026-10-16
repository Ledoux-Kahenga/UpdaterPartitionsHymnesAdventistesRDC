#!/usr/bin/env python3
"""Télécharge TOUS les PDF HL / DLG / CH et met à jour le manifeste.

Sources :
  HL  → https://troisanges.com/Musique/HymnesEtLouanges/PDF/H{nnn}.pdf (+ Hs)
  DLG → https://troisanges.com/Musique/DonnezLuiGloire/PDF/D{nnn}.pdf (+ Ds)
  CH  → https://www.hymnal.pro/church-hymnal-1940/pdf/{n}.pdf

Usage :
  python remote_partitions/fetch_hl_dlg_ch.py            # inventaire + téléchargement
  python remote_partitions/fetch_hl_dlg_ch.py --dry-run  # inventaire seulement
  python remote_partitions/fetch_hl_dlg_ch.py --recueils HL,CH
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
DB = ROOT / "assets" / "HymnesAdventistesDataBase_20261015_170602.db"

UA = "Mozilla/5.0 (compatible; HymnesPartitionsBot/1.0; +local)"
TIMEOUT = 45

RECUEILS = {
    "HL": {
        "table": "HLTb",
        "folder": "hl",
        "key": "HLTb",
        "html": "https://troisanges.com/Musique/HymnesEtLouanges/H{nnn}.html",
        "pdf_base": "https://troisanges.com/Musique/HymnesEtLouanges/PDF/",
        "prefix": "H",
    },
    "DLG": {
        "table": "DLGTb",
        "folder": "dlg",
        "key": "DLGTb",
        "html": "https://troisanges.com/Musique/DonnezLuiGloire/D{nnn}.html",
        "pdf_base": "https://troisanges.com/Musique/DonnezLuiGloire/PDF/",
        "prefix": "D",
    },
    "CH": {
        "table": "CHTb",
        "folder": "ch",
        "key": "CHTb",
        "html": None,
        "pdf_base": "https://www.hymnal.pro/church-hymnal-1940/pdf/",
        "prefix": None,
    },
}


def hymn_numbers(table: str) -> list[int]:
    con = sqlite3.connect(DB)
    cols = [r[1] for r in con.execute(f"PRAGMA table_info([{table}])")]
    num_col = "numberLyric" if "numberLyric" in cols else "number"
    rows = con.execute(
        f"SELECT [{num_col}] FROM [{table}] ORDER BY CAST([{num_col}] AS INTEGER)"
    ).fetchall()
    return [int(r[0]) for r in rows if str(r[0]).isdigit()]


def http_get(url: str) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b"", {}
    except Exception:
        return -1, b"", {}


def http_head(url: str) -> tuple[int, int]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception:
        # Certains serveurs refusent HEAD → essayer GET partiel via GET
        code, data, headers = http_get(url)
        if code == 200:
            return 200, len(data)
        return code, 0


def scrape_troisanges_pdfs(html_url: str, prefix: str, nnn: str) -> list[dict]:
    """Retourne [{label, file, url}] depuis la page HTML du chant."""
    code, body, _ = http_get(html_url)
    if code != 200 or not body:
        return []
    html = body.decode("latin-1", errors="replace")
    parts: list[dict] = []
    seen: set[str] = set()

    for m in re.finditer(
        r"""PDFWindow\(\s*['"]([^'"]+\.pdf)['"]\s*\)[^>]*>\s*([^<]*)""",
        html,
        re.I,
    ):
        url = m.group(1).strip()
        label = re.sub(r"\s+", " ", m.group(2).strip()) or "Partition"
        file_name = url.rstrip("/").split("/")[-1]
        key = file_name.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append({"label": label, "file": file_name, "url": url})

    # Secours : liens .pdf directs
    for m in re.finditer(
        rf"""['"](https?://[^'"]*/PDF/{re.escape(prefix)}{re.escape(nnn)}[A-Za-z0-9_-]*\.pdf)['"]""",
        html,
        re.I,
    ):
        url = m.group(1)
        file_name = url.rstrip("/").split("/")[-1]
        key = file_name.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(
            {
                "label": f"Partition {len(parts) + 1}",
                "file": file_name,
                "url": url,
            }
        )

    return parts


def discover_troisanges(cfg: dict, numbers: list[int]) -> dict[int, list[dict]]:
    """Inventaire exhaustif via HTML + fallback HEAD Hnnn / Hnnns."""
    index: dict[int, list[dict]] = {}
    prefix = cfg["prefix"]
    pdf_base = cfg["pdf_base"]
    total = len(numbers)
    missing_html = 0
    missing_pdf = 0

    def one(num: int) -> tuple[int, list[dict], str]:
        nnn = f"{num:03d}"
        html_url = cfg["html"].format(nnn=nnn)
        parts = scrape_troisanges_pdfs(html_url, prefix, nnn)
        if parts:
            return num, parts, "html"

        # Fallback : tester fichier principal + variantes s / ss / s2
        candidates = [
            f"{prefix}{nnn}.pdf",
            f"{prefix}{nnn}s.pdf",
            f"{prefix}{nnn}ss.pdf",
            f"{prefix}{nnn}s2.pdf",
            f"{prefix}{nnn}_2.pdf",
        ]
        found: list[dict] = []
        for i, name in enumerate(candidates):
            url = pdf_base + name
            code, size = http_head(url)
            if code == 200 and size > 500:
                label = "Partition" if i == 0 else f"Partition {i + 1}"
                if i == 0 and not found:
                    label = "Partition"
                found.append({"label": label, "file": name, "url": url})
        if found:
            if len(found) > 1:
                for i, p in enumerate(found, start=1):
                    p["label"] = f"Partition {i}"
            return num, found, "head"
        return num, [], "miss"

    print(f"  Inventaire {cfg['key']} ({total} chants)…", flush=True)
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(one, n) for n in numbers]
        done = 0
        for fut in as_completed(futs):
            num, parts, how = fut.result()
            done += 1
            if parts:
                index[num] = parts
            else:
                missing_pdf += 1
            if how == "miss":
                missing_html += 1
            if done % 50 == 0 or done == total:
                print(
                    f"    {done}/{total} OK={len(index)} miss={missing_pdf}",
                    flush=True,
                )
    print(
        f"  -> {len(index)}/{total} avec PDF, manquants={missing_pdf}",
        flush=True,
    )
    return index


def discover_ch(numbers: list[int]) -> dict[int, list[dict]]:
    """Church Hymnal : 1 PDF par n° sur hymnal.pro."""
    index: dict[int, list[dict]] = {}
    base = RECUEILS["CH"]["pdf_base"]
    total = len(numbers)
    print(f"  Inventaire CHTb ({total} chants)...", flush=True)

    def one(num: int) -> tuple[int, list[dict]]:
        name = f"{num}.pdf"
        url = base + name
        code, size = http_head(url)
        if code != 200 or size < 500:
            # Certains serveurs refusent HEAD : GET
            code2, data, _ = http_get(url)
            if code2 == 200 and len(data) > 500:
                return num, [
                    {"label": "Partition", "file": name, "url": url, "_bytes": data}
                ]
            return num, []
        return num, [{"label": "Partition", "file": name, "url": url}]

    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(one, n) for n in numbers]
        done = 0
        for fut in as_completed(futs):
            num, parts = fut.result()
            done += 1
            if parts:
                index[num] = parts
            if done % 50 == 0 or done == total:
                print(f"    {done}/{total} OK={len(index)}", flush=True)
    print(f"  -> {len(index)}/{total} avec PDF", flush=True)
    return index


def download_all(
    folder: Path,
    index: dict[int, list[dict]],
    dry_run: bool,
) -> tuple[int, int, int]:
    """Télécharge chaque fichier unique. Retourne (ok, skip, fail)."""
    folder.mkdir(parents=True, exist_ok=True)
    # url/file uniques
    files: dict[str, str] = {}  # file -> url
    inline: dict[str, bytes] = {}
    for parts in index.values():
        for p in parts:
            files[p["file"]] = p["url"]
            if "_bytes" in p:
                inline[p["file"]] = p["_bytes"]

    ok = skip = fail = 0
    items = sorted(files.items())
    total = len(items)
    print(f"  Telechargement {total} fichiers -> {folder}", flush=True)

    def one(name: str, url: str) -> tuple[str, str]:
        dest = folder / name
        if dest.exists() and dest.stat().st_size > 500:
            return name, "skip"
        if dry_run:
            return name, "dry"
        if name in inline:
            dest.write_bytes(inline[name])
            return name, "ok"
        for attempt in range(3):
            code, data, _ = http_get(url)
            if code == 200 and len(data) > 500:
                dest.write_bytes(data)
                return name, "ok"
            time.sleep(0.8 * (attempt + 1))
        return name, "fail"

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(one, n, u) for n, u in items]
        done = 0
        for fut in as_completed(futs):
            name, status = fut.result()
            done += 1
            if status == "ok":
                ok += 1
            elif status in ("skip", "dry"):
                skip += 1
            else:
                fail += 1
                print(f"    FAIL {name}", flush=True)
            if done % 40 == 0 or done == total:
                print(
                    f"    {done}/{total} ok={ok} skip={skip} fail={fail}",
                    flush=True,
                )
    return ok, skip, fail


def merge_manifest(
    new_hymnals: dict[str, dict],
) -> Path:
    """Fusionne HL/DLG/CH dans manifest.json existant (SDAH/NZK)."""
    path = OUT / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "version": 2,
            "source": "Partitions_",
            "hymnals": {},
        }

    version = int(manifest.get("version") or 2) + 1
    manifest["version"] = version
    manifest["notes"] = (
        "startPage/endPage 1-based pour SDAH multi ; "
        "HL/DLG/CH = 1 fichier (ou Partition N) par entrée"
    )
    hymnals = manifest.setdefault("hymnals", {})
    for key, data in new_hymnals.items():
        hymnals[key] = data

    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "version.txt").write_text(str(version), encoding="utf-8")
    return path


def index_to_manifest_block(
    folder: str,
    index: dict[int, list[dict]],
) -> dict:
    hymns = {}
    for num in sorted(index):
        entries = []
        for p in index[num]:
            entries.append(
                {
                    "label": p["label"],
                    "file": p["file"],
                    "startPage": 1,
                    "endPage": 1,
                }
            )
        hymns[str(num)] = entries
    return {
        "folder": folder,
        "count": len(hymns),
        "hymns": hymns,
    }


def verify_disk(folder: Path, index: dict[int, list[dict]]) -> list[str]:
    missing = []
    for num, parts in index.items():
        for p in parts:
            f = folder / p["file"]
            if not f.exists() or f.stat().st_size < 500:
                missing.append(f"{num}:{p['file']}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--recueils",
        default="HL,DLG,CH",
        help="Liste séparée par virgules : HL,DLG,CH",
    )
    args = parser.parse_args()
    wanted = {x.strip().upper() for x in args.recueils.split(",") if x.strip()}

    new_blocks: dict[str, dict] = {}
    report: list[str] = []

    for code in ("HL", "DLG", "CH"):
        if code not in wanted:
            continue
        cfg = RECUEILS[code]
        nums = hymn_numbers(cfg["table"])
        print(f"\n=== {cfg['key']} : {len(nums)} chants ===", flush=True)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

        if code == "CH":
            index = discover_ch(nums)
        else:
            index = discover_troisanges(cfg, nums)

        dest = OUT / cfg["folder"]
        ok, skip, fail = download_all(dest, index, dry_run=args.dry_run)
        missing = [] if args.dry_run else verify_disk(dest, index)

        # Relabel Partition 1..N
        for parts in index.values():
            if len(parts) > 1:
                for i, p in enumerate(parts, start=1):
                    p["label"] = f"Partition {i}"

        new_blocks[cfg["key"]] = index_to_manifest_block(cfg["folder"], index)
        line = (
            f"{cfg['key']}: DB={len(nums)} avec_pdf={len(index)} "
            f"fichiers_ok={ok}+skip={skip} fail={fail} "
            f"manquants_disque={len(missing)}"
        )
        report.append(line)
        print(line, flush=True)
        if missing[:20]:
            print("  manquants:", ", ".join(missing[:20]), flush=True)
        sans = [n for n in nums if n not in index]
        if sans:
            print(
                f"  Sans PDF côté source ({len(sans)}): "
                f"{sans[:30]}{'…' if len(sans) > 30 else ''}",
                flush=True,
            )

    if not args.dry_run and new_blocks:
        path = merge_manifest(new_blocks)
        print(f"\nManifest mis à jour : {path}", flush=True)

    print("\n=== RAPPORT ===")
    for line in report:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
