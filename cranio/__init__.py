# -*- coding: utf-8 -*-
"""cranio - Framework de reconstructie craniofaciala.

Pachet Python pur (fara dependinte de Blender), extras din scriptul
monolitic ``gnm_reconstruct.py`` (v3.1). Arhitectura urmeaza principiile
din TODO.md:

    * fiecare modul are o singura responsabilitate;
    * modulele comunica doar prin modele de date partajate;
    * optimizorul nu stie nimic de Blender;
    * backend-ul de model facial (GNM) nu stie nimic de cranii.

Module:
    landmarks   - registru anatomic unic (etichete, adancimi, ponderi).
    backend     - interfata abstracta FaceModelBackend + implementarea GNM.
    io_csv      - citire/scriere fisiere de markeri (legacy v11/v12 + v2).
    geometry    - utilitare de mesh (normale, masti de regiuni, cranii).
    checks      - verificari de consistenta a plasarii markerilor.
    optimize    - aliniere, fit statistic, corectie TPS, termeni de loss.
    config      - PipelineConfig (configuratia completa a unei rulari).
    export      - export OBJ / PLY heatmap.
    report      - raport TXT de reconstructie.
    pipeline    - fluxul complet end-to-end (folosit de CLI si de Blender).
"""


__version__ = "5.0.0rc2"
