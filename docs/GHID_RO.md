# Ghid rapid în română: 5.0.0rc3 / addon 16

Addon-ul oferă **48 de markeri**, pipeline offline și verificarea mediului Python înainte de calcul. Tabelul 2 din PDF are 21 de tipuri anatomice, adică **32 de poziții**: 10 mediane și 11 perechi bilaterale. Reunirea lor cu cei 27 de markeri anteriori adaugă 21 de poziții noi.

## Instalare și eroarea Windows

1. Din repository, creează un mediu Python 3.12 pe calculatorul Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
(Resolve-Path .\.venv\Scripts\python.exe).Path
```

2. Obține modelul oficial conform [INSTALL](INSTALL.md), apoi verifică-l cu `.\.venv\Scripts\python.exe -m cranio.doctor --npz models\gnm_head.npz`. Modelul se păstrează local și nu este inclus în addon.
3. Instalează `gnm_cranio-5.0.0rc3.zip` în Blender prin **Install from Disk** și activează **GNM Scientific Markers**. Dezactivează copia veche înainte de înlocuire. Pentru construirea ZIP-ului din surse: `python tools/build_addon.py`.
4. La **Python executable / venv folder**, selectează `python.exe` din `.venv\Scripts`, sau directorul `.venv` creat pe Windows. Poți lipi calea afișată de ultima comandă de mai sus.
5. Apasă **Check Python Environment**. Rezultatul trebuie să confirme Python 3.10+ pe 64 de biți și `numpy/scipy/trimesh OK`.

Mesajul `%1 is not a valid Win32 application` este eroarea de lansare Windows 193 și apare înainte de fit. Versiunea anterioară verifica numai existența fișierului. În acel câmp nu se introduce `gnm_reconstruct.py`, `blender.exe`, fișierul de activare sau installerul Python. Nici un mediu Linux/macOS copiat nu funcționează ca interpretor Windows. Noua versiune respinge aceste selecții, verifică dependențele și afișează un diagnostic concret. Fără calea selectată pe stația ta nu se poate stabili care dintre aceste situații a produs eroarea inițială.

Pentru instalare complet offline, pregătește kitul de dependențe pe aceeași platformă, conform [INSTALL](INSTALL.md).

## Markerii și valorile din PDF

Alege **Extended 48**, **VAR 2026 Table 2: 32** sau **Legacy 27**, apoi **Add Missing Markers**. Butonul adaugă numai reperele lipsă; păstrează obiectele, grosimile introduse și selecțiile manuale de vertex. Alegerea unui set mai mic nu șterge lista existentă.

Într-o scenă nouă, setul Paper 32 folosește valorile din tabel. În Extended 48, valorile vechilor 27 se păstrează, iar cele 21 noi au sursa din PDF. **Apply Table 2 Tissue Depths** aplică explicit tabelul la toate reperele corespunzătoare și actualizează țintele deja plasate; operația permite Undo.

Tabelul este referința „normal, female”, provenită din date Southwestern Native American, utilizată în cazul studiat. Nu este un tabel universal sau un set de măsurători al populației din România. Verifică aplicabilitatea și direcția de măsurare. Nu confunda Suborbitale cu foramenul infraorbital, LateralOrbit cu colțul ochiului sau Menton cu Gnathion.

PDF-ul nu conține corespondențe GNM. Candidații noi trebuie inspectați pe model și pot fi corectați prin **Pick GNM Vertex**. Candidatul implicit Pogonion a fost corectat: 12284 aparține buzei inferioare în GNM; noul candidat pentru bărbie este 12261. Selecțiile manuale și indicii expliciți din CSV v3 sunt respectați. Revizuiește cazurile vechi.

## Lucrul pe caz

Importă craniul alegând unitățile sursei și verifică o dimensiune cunoscută. Scena folosește 1 coordonată Blender = 1 mm, cu scala metrică 0,001. Plasează reperele pe os, verifică țintele cutanate, direcțiile și grosimile. La Midphiltrum, definiția din articol este de țesut moale: proiecția pe os necesită o alegere explicită a specialistului.

Pentru fiecare reper, completează **Bone provenance** (observat, reparat digital sau inferat), notele și sursa țesutului. Bifează **Skin correspondence reviewed** după revizie. **Include in fit** poate fi dezactivat pentru repere păstrate numai în documentație; acestea nu intră în alinierea și fitul numeric. Greutatea controlează influența relativă, fără a reprezenta o probabilitate.

Înregistrează modificarea craniană și reparațiile în câmpurile cazului. Modelul GNM general poate să nu reprezinte o boltă craniană modificată intenționat. Păstrează scanarea originală și evaluează separat constrângerile de pe boltă.

Selectează directorul cazului, apoi **Run Offline Fit and Import**. Sunt necesari cel puțin patru markeri plasați și incluși; acest minim numeric nu garantează suficiența anatomică. Fiecare rulare creează un subdirector cu `run.log`, mesh-uri și raport JSON. Calculul poate fi anulat.

```bash
python gnm_reconstruct.py --input markeri.csv --npz models/gnm_head.npz --output outputs/caz01/fata.obj --strict
```

`--strict` verifică trasabilitatea și respinge corespondențele incluse marcate explicit ca nerevizuite. Nu certifică științific valorile introduse.

## Rezultate și limite

- `fata_statistical.obj`: rezultatul modelului statistic.
- `fata.obj`: rezultatul final; identic implicit cu cel statistic.
- `fata_heatmap.ply`: amplitudinea corecției locale, nu incertitudinea sau eroarea față de fața reală.
- `fata_statistici.txt`: diagnostice pentru specialist.
- `fata_report.json`: parametri, versiuni, amprente, proveniență, repere excluse și reziduuri.

RMSE mic arată potrivirea la țintele introduse. Numărul mai mare de markeri nu demonstrează automat acuratețe mai bună. Verificarea interactivă pe stația de lucru și validarea pe cazuri independente rămân necesare. [Protocolul bazat pe PDF](PDF_PROTOCOL.md) delimitează implementarea de metodele anatomice și artistice care nu au fost automatizate.

## Cranii fragmentare, duplicate și lambda

Nu mai există alegerea unei jumătăți globale de păstrat. Pentru craniu drept + os nazal + mandibulă stângă, creează trei regiuni prin **Add Active Fragment**: craniu drept cu **Mirror selected region**, os nazal cu **Keep preserved**, mandibulă stângă cu **Mirror selected region**. Poți folosi obiecte separate sau grupuri de vertecși în același mesh. Înregistrează toate fragmentele păstrate.

Mandibula nearticulată necesită propriul obiect-plan; numai după verificarea articulației poți bifa **Mandible articulated with cranium**. Planul unui obiect este planul său local XY. Completările se generează separat; originalele nu sunt tăiate, ascunse sau sudate. Verifică îmbinările și repoziționează/reverifică markerii după modificarea fragmentelor. Detaliile și limitele filtrului de suprapuneri sunt în [FRAGMENT_RESTORATION](FRAGMENT_RESTORATION.md).

**Audit Landmark Duplicates** verifică selecțiile manuale și țintele coincidente. Catalogul are 48 de etichete și 48 de vertecși unici; Nasospinale și Acanthion au candidații cutanați la 1,5 mm distanță și necesită verificarea definițiilor pe os.

Lambda implicit este `lambda_bază × 48 / N_folosit`, limitat de minim/maxim: cu baza 1, pentru 12 repere lambda este 4; pentru 24 este 2; pentru 48 este 1. Se numără doar reperele plasate, mapate, distincte și incluse. Punctele dense și reperele excluse nu măresc numărul. Regula este o euristică; opțiunea LOO rămâne separată. Butonul offline transmite explicit modul ales.
