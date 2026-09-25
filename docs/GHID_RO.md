# Ghid rapid în română

Versiunea nouă oferă un pipeline offline verificabil și un addon complet ambalat. **Nu reprezintă încă un sistem validat pentru acuratețe medico-legală pe cazuri reale.** Modelul GNM descrie variația capului; nu oferă singur o relație validată craniu–față.

## Instalare

1. Creează un mediu Python 3.12 și rulează `python -m pip install .` din repository.
2. Obține modelul GNM oficial și verifică amprenta, conform [INSTALL.md](INSTALL.md). Modelul nu este inclus în ZIP.
3. Rulează `python tools/build_addon.py`. În Blender instalează `dist/gnm_cranio-5.0.0rc1.zip`, apoi activează **GNM Scientific Markers**. ZIP-ul include și pachetul numeric.
4. Selectează modelul local. Importă craniul alegând explicit unitățile fișierului. Verifică o dimensiune cunoscută. Scena de lucru folosește 1 unitate Blender = 1 mm, cu scala metrică 0,001.

## Lucrul pe caz

Plasează reperele pe os și verifică țintele cutanate, direcția și grosimea țesutului. Valorile precompletate sunt ipoteze moștenite, fără trasabilitate completă la tabele științifice; trebuie revizuite. Completează câmpul **Tissue source / method** pentru fiecare reper folosit.

Modificarea grosimii actualizează ținta deja plasată. Corecțiile manuale ale vertexului GNM sunt păstrate în noul CSV v3, alături de poziția pe os, ținta de piele și amprenta modelului.

Pentru calculul final, selectează executabilul Python al mediului creat și directorul cazului, apoi **Run Offline Fit and Import**. Calculul rulează într-un proces separat, iar rezultatul este importat în aceleași coordonate. Fiecare rulare primește un subdirector nou și un jurnal `run.log`. Butonul folosește potrivirea statistică pe markeri; opțiunile avansate se rulează din CLI.

```bash
python gnm_reconstruct.py --input markeri.csv --npz models/gnm_head.npz --output outputs/caz01/fata.obj --strict
```

## Interpretare

- `fata_statistical.obj`: rezultatul modelului statistic, înaintea deformării locale.
- `fata.obj`: rezultatul final; identic cu cel statistic în setarea implicită.
- `fata_heatmap.ply`: amplitudinea deformării locale, **nu incertitudinea** și nu eroarea față de fața reală.
- `fata_statistici.txt`: diagnosticele pentru specialist.
- `fata_report.json`: parametri, coeficienți, transformare, versiuni, amprente și reziduuri.

RMSE mic la markeri arată potrivirea la țintele introduse. Nu demonstrează că fața persoanei a fost recuperată. Corecția locală se activează numai explicit, cu `--local-correction`; comparați întotdeauna cele două mesh-uri.

[Fundamentarea științifică](SCIENCE.md), [protocolul pentru specialist](SPECIALIST_WORKFLOW.md), [auditul](AUDIT.md) și [validarea necesară](VALIDATION.md) explică ipotezele și limitele. Verificarea addon-ului într-un Blender real rămâne un pas de acceptanță obligatoriu pe stația de lucru.
