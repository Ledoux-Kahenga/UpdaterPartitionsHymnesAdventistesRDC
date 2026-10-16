# Partitions PDF (hébergement distant)

Partitions **SDAH**, **Nyimbo za Kristo**, **Hymnes et Louanges**, **Donnez-Lui Gloire** et **Church Hymnal** — hors APK, servies via GitHub raw + cache local.

## Repo

```
https://github.com/Ledoux-Kahenga/UpdaterPartitionsHymnesAdventistesRDC
```

URL app (`AppConstants.partitionsBaseUrl`) :

```
https://raw.githubusercontent.com/Ledoux-Kahenga/UpdaterPartitionsHymnesAdventistesRDC/main/
```

## Arborescence

```
version.txt
manifest.json
sdah/          SDAH (scoreNNN.pdf, score013m_014.pdf, …)
nzk/           Nyimbo za Kristo
hl/            Hymnes et Louanges (H001.pdf, H001s.pdf, …) — source Trois Anges
dlg/           Donnez-Lui Gloire (D001.pdf, …) — source Trois Anges
ch/            Church Hymnal 1940 (1.pdf … 702.pdf) — source hymnal.pro
```

## Couverture

| Recueil | Clé manifeste | Chants DB | PDF |
|---------|---------------|-----------|-----|
| SDAH | `SDAH` | ~695 | fichiers `score*` (certains multi-n°) |
| NZK | `NZKristoTb` | 220 | `NyimboZaKristo-N.pdf` |
| Hymnes et Louanges | `HLTb` | 654 | 100 % (+ variantes `s`) |
| Donnez-Lui Gloire | `DLGTb` | 520 | 100 % |
| Church Hymnal | `CHTb` | 703 | 702 — **703 absent sur hymnal.pro** |

## Scripts

```bash
# HL + DLG + CH (téléchargement exhaustif)
python remote_partitions/fetch_hl_dlg_ch.py

# SDAH / NZK depuis assets/Partitions_/
python remote_partitions/build_manifest.py --copy

# Rebuild manifeste depuis le disque
python remote_partitions/rebuild_manifest_from_disk.py
```

## Notes

- `startPage` / `endPage` (1-based) : pages à afficher pour un PDF SDAH partagé (ex. 14 → page 2 de `score013m_014.pdf`).
- HL / DLG : plusieurs fichiers par chant si `Hnnns.pdf` / `Dnnns.pdf` existent.
- CH **703** (*The Lord Is in His Holy Temple*) : page lyrics sur hymnal.pro, **pas de PDF** côté source.
