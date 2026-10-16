# Partitions PDF (hébergement distant)

Les meilleures partitions **SDAH** et **Nyimbo za Kristo** (~113 Mo) ne doivent **pas** être embarquées dans l’APK.

## Stratégie (même modèle que les textes)

Repo GitHub dédié (recommandé) :

```
https://github.com/Ledoux-Kahenga/UpdaterPartitionsHymnesAdventistesRDC
```

URL raw utilisée par l’app (`AppConstants.partitionsBaseUrl`) :

```
https://raw.githubusercontent.com/Ledoux-Kahenga/UpdaterPartitionsHymnesAdventistesRDC/main/
```

### Arborescence du repo

```
version.txt          → 1
manifest.json        → n° chant → fichiers PDF
sdah/score002.pdf
sdah/score013m_014.pdf
…
nzk/NyimboZaKristo-1.pdf
nzk/NyimboZaKristo-26a.pdf
…
```

## Préparer la publication

Depuis la racine du projet Flutter :

```bash
# 1. Régénère le manifeste
python remote_partitions/build_manifest.py

# 2. Copie les PDF dans remote_partitions/sdah et nzk (~113 Mo)
python remote_partitions/build_manifest.py --copy
```

Puis crée le repo GitHub (une fois) et pousse :

```bash
cd remote_partitions
git init
git add version.txt manifest.json sdah nzk README.md
git commit -m "Partitions SDAH + NZK"
git branch -M main
git remote add origin https://github.com/Ledoux-Kahenga/UpdaterPartitionsHymnesAdventistesRDC.git
git push -u origin main
```

> Astuce : repo **public** pour que `raw.githubusercontent.com` fonctionne sans token.

## Noms de fichiers

| Recueil | Exemple | Remarque |
|---------|---------|----------|
| SDAH | `score042.pdf` | Un fichier peut couvrir plusieurs n° : `score013m_014.pdf` |
| NZK | `NyimboZaKristo-26.pdf` | Variantes : `26a`, `137m`, `4ma` |

Le `manifest.json` mappe chaque numéro vers la/les fiche(s) à télécharger.

## Pourquoi pas dans l’APK ?

| | APK | GitHub + cache |
|-|-----|----------------|
| Taille install | +113 Mo | inchangée |
| Mise à jour | nouveau build | `git push` |
| Lecture | offline immédiat | 1er téléchargement puis cache |

## Alternatives

- **GitHub Releases** : 1 zip SDAH + 1 zip NZK (bon si tu préfères un gros téléchargement unique).
- **Cloudflare R2 / Firebase Storage** : si la bande passante GitHub devient limitée.
