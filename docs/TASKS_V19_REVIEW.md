# GNM Craniofacial Approximation — analiza TASKS.md și plan revizuit

Data: 29 octombrie 2026. Cod analizat: `main`, commit
`49a8ac1dfe263ef5c7c176a513fc05b67dc858e2`, addon 19.0.0 / pachet 5.0.0rc10.

Acesta este un document de analiză și specificare raportat la commit-ul de mai sus.
Funcțiile noi propuse nu sunt încă implementate. După audit au fost implementate
două corecții de trasabilitate într-o ramură separată; vezi secțiunea 9.

## Concluzie

Lista propusă este utilă, dar descrie o bază V13.5 depășită și amestecă funcții
existente, dezvoltare software, alegeri anatomice și validare pe subiecți.
Recomand păstrarea arhitecturii curente și extinderea ei incrementală. Nu este
necesară rescrierea pipeline-ului sau revenirea numerotării la V14.

Conform instrucțiunii autorului, validarea pe cazuri CT rămâne o activitate
manuală separată. Implementarea software trebuie verificată prin teste numerice,
geometrii sintetice, modelul oficial și Blender real. Absența unui studiu CT nu
blochează dezvoltarea, dar împiedică etichetarea rezultatului drept validat pe
persoane sau a intervalelor drept calibrate clinic/anatomic.

## 1. Baza verificată efectiv

| Verificare | Rezultat la această revizie |
| --- | --- |
| `pytest`, cu modelul oficial | 211 trecute, 1 test nativ Windows omis pe Linux |
| Ruff, configurația proiectului | Trecut |
| Construire ZIP și instalare în Blender 4.5.0 Linux | Trecut |
| Suita Blender completă | `BLENDER_SMOKE_PASS` |
| Fit extern, import și anulare | `BLENDER_EXTERNAL_FIT_IMPORT_CANCEL_PASS` |
| Controale post-fit, UV, reset, persistență, textură | `BLENDER_POSTFIT_PRESENTATION_PASS` |
| Ajustarea procentuală a grosimilor și Undo | Trecut |
| Cazuri CT ale autorului | Neevaluate în această analiză |
| Utilizare interactivă pe stația Windows a autorului | Neevaluată în această analiză |

Mediu local: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0,
pytest 9.2.0. Blender 4.5.0, build `8cb6b388974a`, arhivă verificată față de
checksum-ul oficial. Aceste versiuni descriu execuția locală; nu s-a modificat
fișierul de dependențe fixate al proiectului.

Model verificat SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.

Comenzile principale:

```bash
GNM_MODEL_PATH=/cale/gnm_head.npz OPENBLAS_NUM_THREADS=1 python -m pytest -q
python -m ruff check cranio addon_v13.py gnm_reconstruct.py tools tests
python tools/build_addon.py
GNM_MODEL_PATH=/cale/gnm_head.npz GNM_EXTERNAL_PYTHON=/cale/python \
  OPENBLAS_NUM_THREADS=1 blender --background --factory-startup \
  --python-exit-code 1 --python tools/blender_smoke.py
```

Valorile istorice 57/57 și 46/47 nu mai sunt o bază de acceptare pentru această
revizie. Fișierele `test_addon_v13_headless.py` și `v13-test/` nu sunt prezente
în checkout-ul actual; integrarea Blender folosește `tools/blender_smoke.py`
și modulele sale de verificare.

## 2. Răspunsurile auditului T0.1

Toate referințele `fișier:linie` de mai jos se referă la commit-ul indicat sus.
Sursa poate fi consultată la:
https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/tree/49a8ac1dfe263ef5c7c176a513fc05b67dc858e2

1. **Repere:** 48 de poziții tisulare, cu seturi alternative Paper 32 și Legacy 27;
   separat, 22 de repere osoase pentru 14 măsurători. Includerea în fit depinde
   de plasare, corespondență și `use_for_fit`. Reperele osoase nu devin automat
   ținte cutanate. Dovezi: `cranio/landmarks.py:186`, `:208`,
   `cranio/craniometry.py:17`, `:50`, `cranio/io_csv.py:140`.
2. **Grosimi:** valorile moștenite și ponderile sunt în `cranio/landmarks.py:23`,
   `:60`, `:136`; Table 2 și metadatele sale în `cranio/paper_reference.py:17`.
   Scalp offset implicit 5 mm în `cranio/config.py:42`. Există proveniență parțială,
   nu un registru general de tabele cu SD și direcții. Nu trebuie atribuită o SD
   valorilor existente în absența unei surse.
3. **Direcții:** plasarea inițială utilizează estimarea normalei locale sau
   alternativa configurată; direcția aplicată este documentată. Operatorul poate
   ulterior modifica markerul. Dense folosește punctul de os plus offset pe
   normala osoasă verificată. Dovezi: `addon_v13.py:665`,
   `cranio/blender_marker_normals.py:24`, `:75`, `:105`,
   `cranio/geometry.py:134`, `:160`. Nu există încă alegerea direcției dintr-un
   registru de tabele tisulare.
4. **Identitate:** solverul rezolvă toate rândurile bazei primite; backend-ul
   livrează cele 253 de componente. Numărătoarea `clip` include toate componentele.
   Dovezi: `cranio/optimize.py:298`, `:420`, `:557`, `addon_v13.py:2520`.
   În NPZ am verificat efectiv numele și indicii: head 0–169 (170), eyes 170–172
   (3), teeth 173–252 (80). Opțiunea `identity-subspace=head` lipsește.
5. **Scală:** provine din Umeyama ponderat; când sunt active distanțele cutanate,
   este actualizată și cu acel termen. Este verificată numeric ca pozitivă și
   nedegenerată, fără un interval anatomic configurat. Dovezi:
   `cranio/optimize.py:58`, `:87`, `:311`, `cranio/measurement_fit.py:53`.
6. **Corecție locală:** implicit oprită; caps 8 mm față / 15 mm scalp;
   amortizare 0,25 pe grupurile protejate. Interpolatorul efectiv utilizează
   `kernel='linear'` (−r), grad 1, smoothing 0, urmat de limitarea tanh.
   Dovezi: `cranio/config.py:35`, `cranio/optimize.py:481`, `:514`, `:520`,
   `cranio/landmarks.py:130`.
7. **Live/offline:** folosesc același `fit_identity`, prin adaptorul
   `cranio/preview.py`. Diferențele de flux rămân: live admite regim markerless
   cu dense și minimum trei markeri pentru aliniere; offline cere minimum patru;
   CLI direct are LOO implicit, UI are lambda adaptivă implicit; corecția locală
   finală și QC complet sunt în fluxul offline. Același solver nu înseamnă
   rezultate identice cu date/setări diferite. Dovezi: `cranio/preview.py:9`,
   `addon_v13.py:2499`, `:3365`, `:3763`, `cranio/pipeline.py:194`, `:357`.
8. **Prior:** este deja dezactivat implicit. CLI îl încarcă numai cu `prior`,
   UI folosește `NONE`, iar solverul aplică penalizarea față de media și scala
   priorului. Butonul offline transmite priorul selectat. Dovezi:
   `cranio/config.py:63`, `cranio/pipeline.py:116`, `cranio/optimize.py:390`,
   `addon_v13.py:2985`, `:3370`, `:3781`.

Testul vechi de simetrie exactă nu mai este un eșec curent. Testul actual verifică
perechile topologice și o toleranță pentru micro-asimetria template-ului:
`tests/test_official_model.py`. Pe cele 17 perechi ale setului actual am măsurat
maximul **0,234097050969527 mm**; pragul software existent este 0,25 mm.
Acest rezultat nu validează corespondența anatomică a markerilor.

## 3. Matricea TASKS.md → implementarea actuală

„Parțial” înseamnă că există o componentă reutilizabilă, nu că toate criteriile
de acceptare din task sunt îndeplinite.

| Task | Stare | Ce trebuie păstrat / adăugat |
| --- | --- | --- |
| T0.1 | Audit istoric existent; actualizare necesară | `docs/AUDIT.md` este din septembrie. Nu crea simultan `audit.md`: coliziune de nume pe Windows. |
| T0.2 | Parțial | Exemple sintetice și teste end-to-end există; lipsește runnerul comparativ cu configurații externe. CT-urile nu sunt o condiție pentru dezvoltare. |
| T0.3 | Parțial | `quality.py` are reversări de normale, degenerări, contacte și clearance local. Lipsesc interfața unitară, unele metrici regionale/profil și unghiul minim. |
| A1.1–A1.3 | Parțial | Există un tabel citat și selecția/aplicarea lui; lipsesc schema generală, migrarea tuturor constantelor și comparația între tabele. |
| A1.4 | Lipsește | Nu există ponderare explicită după SD. Ponderile curente sunt influențe relative. |
| A1.5 | Parțial | Normale și proveniența direcției există; lipsește direcția definită de fiecare sursă tisulară. |
| A1.6 | Parțial | Există unele metadate de populație/sex; lipsesc estimatorul, postura și verificarea lor sistematică. |
| A2.1–A2.4 | Lipsește | Nu există ansamblu Monte Carlo, covarianță, calibrare sau intervale predictive. Heatmap-ul actual este corect etichetat drept deplasare. |
| A3.1–A3.4 | Lipsește ca sistem general | Există diagnosticul nazal informativ, fără registru general de reguli, erori validate și comparator pentru toate trăsăturile. |
| A4.1 | Parțial | CSV v3 există. Supramentale, Infradentale și Menton există; Basion/Bregma/Opisthocranion/Frontotemporale există în registrul osos. Adăugăm doar reperele distincte lipsă. |
| A4.2 | Parțial | Plan mediosagital pe repere observate și RMS există; cadrul Frankfort și incertitudinea sa lipsesc. |
| A4.3 | Lipsește | Cele 14 coarde nu sunt echivalente cu indicii/angulațiile cefalometrice propuse. |
| A4.4 | Lipsește | Nu există constrângere explicită de profil sagital. |
| A4.5 | Parțial | Mandibula poate avea plan separat și confirmarea articulației; lipsesc instrumentul dedicat condil–fosă și verificarea contactului dentar. |
| A4.6 | Lipsește | Nu există eșantionarea sensibilității la poziția mandibulei. |
| A4.7 | Lipsește | Fitul utilizează toate cele 253 de componente. |
| A5 | Parțial | Există validări, strict, protocol înghețat și QC obligatoriu; lipsește contractul unic pass/warn/block/override și intervalele anatomice configurate. |
| A6 | Parțial | Priorul neutru este deja implicit. Lipsesc comparația neutral/prior, justificarea obligatorie și tratarea structurată a vârstei. |
| A7.1 | Substanțial, dar incomplet | `report.py` și `provenance.py` au versiuni, hash-uri, coeficienți, transformare, setări, reziduuri și metadate. Extindem acest raport, nu construim unul concurent. |
| A7.2 | Lipsește | Nu există un domeniu de validitate alimentat de evaluări independente. Poate rămâne neconfigurat. |
| A7.3 | Parțial | V19 separă copia neutră de prezentarea cu UV/expresii. Lipsesc modurile formale de export, etichetele obligatorii și capturile în Frankfort. |
| B1 | Parțial | Solverul statistic este deja comun. Corecția locală este încă SciPy/offline; lipsește varianta NumPy și operatorul Finalize. |
| B2.1 | Parțial | Există definiții și sugestii de plasare, fără atlas pe craniu de referință. |
| B2.2–B2.4 | Lipsește | ICP-ul actual aliniază GNM, nu transferă repere de pe un atlas osos. Lipsesc propunerile, coada lor de revizie și sesiunile A/B. |
| B3 | Lipsește ca wizard | Există opțiuni pentru fragmente/scalp/mandibulă; nu există scenarii declarative complete. |
| B4 | Parțial | Reutilizăm QC existent; lipsesc panoul unificat, benzile tisulare și corecția explicită opțională. |
| B5 | Parțial | Proveniență pe obiecte/regiuni/markeri există; lipsesc atributele per-față și propagarea calibrată spre ponderi/incertitudine. |
| C1 | Lipsește ca detector | Există raport de asimetrie și câmp de modificare craniană. Acestea nu diagnostichează etiologia sau patologia. |
| C2 | Lipsește | Controalele post-fit pentru dantură nu compară automat dinții GNM cu dentiția observată. |
| C3 | Parțial; CT manual | Există holdout de markeri și protocol documentat, nu un harness complet de validare CT. Păstrăm exporturile necesare evaluării manuale. |
| T-FINAL | De rescris | Packaging, changelog, CI și CSV v3 există. Folosim numerotare ulterioară V19 și o bază nouă fixată prin commit. |

Module importante reutilizabile: `cranio/quality.py`, `cranio/report.py`,
`cranio/provenance.py`, `cranio/protocol.py`, `cranio/craniometry.py`,
`cranio/measurement_fit.py`, `cranio/preview.py`, `cranio/surface_normals.py`,
`cranio/blender_restoration.py`, `cranio/postfit.py`, `cranio/blender_postfit.py`.

## 4. Probleme concrete constatate

### 4.1 Sursă tisulară goală acceptată în strict — reprodus

`cranio/pipeline.py:176` compară șirul cu trei valori exacte. O sursă egală cu
trei spații trece verificarea; `cranio/io_csv.py:132` o păstrează. Pe exemplul
sintetic oficial, cu `strict=True`, rularea a returnat 0 și a scris acea sursă
în raport. Verificarea din `cranio/craniometry.py:195` normalizează deja spațiile
și majusculele. Contractele sunt inconsistente. `protocol.py` are aceeași
comparație limitată pentru sursa tisulară.

**Fix:** funcție comună de validare a provenienței textuale; respingerea șirurilor
goale după strip și a placeholderelor rezervate în strict/protocol. Păstrăm
textul original pentru audit. Teste pentru spații, majuscule și surse reale.
Acest fix modifică acceptarea inputurilor invalide; nu schimbă soluția geometrică
pentru inputurile valide și nu trebuie ascuns în spatele unui flag opțional.

### 4.2 Lambda adaptivă raportată drept fixed — reprodus

`cranio/report.py:158` distinge numai între LOO și absența LOO. O rulare cu
`regularization='adaptive'` este raportată cu `lambda_selection.method='fixed'`.
Configurația păstrează modul corect, dar câmpul rezumat îl contrazice.

**Fix:** moduri explicite fixed/adaptive/conditional_loo, cu numărul de markeri
și parametrii formulei adaptive. Testează consistența JSON–config–UI.

### 4.3 Export CSV înainte de validarea completă — observat în cod

`addon_v13.py:3639` scrie CSV-ul, iar `:3642` îl recitește pentru validare.
`cranio/io_csv.py:159` scrie direct în destinație. Dacă verificarea eșuează,
un fișier invalid poate rămâne la destinație, iar un fișier existent poate fi
înlocuit înainte ca operatorul să raporteze eroarea.

**Fix:** scriere temporară, validare cu același reader și înlocuire atomică numai
după succes. Testul trebuie să demonstreze că destinația anterioară rămâne intactă
la eșec. Nu este necesar niciun prag anatomic nou.

### 4.4 QC obligatoriu nu înseamnă blocarea scrierii mesh-ului

`cranio/pipeline.py:587` exportă mesh-urile, iar `:654` returnează 3 dacă QC
obligatoriu nu a trecut. Raportul are `status='completed'` și QC `needs_review`.
Acesta este comportament intenționat și testat în `tests/test_provenance.py`,
nu un defect nou demonstrat al contractului actual. Totuși, **nu satisface A5**,
care cere blocarea exportului științific.

**Schimbare nouă, explicită:** separă completarea calculului de autorizarea
exportului; permite raport și mesh de diagnostic în zonă/categorie distinctă,
fără a le prezenta drept export științific aprobat. Override-ul trebuie să aibă
motiv și să rămână vizibil. Nu schimbăm retroactiv sensul unui exit code fără
migrare/documentare.

### 4.5 Raport de sesiune cu atribuire greșită

`addon_v13.py:999` spune „default values from the GNM table”. Grosimile sunt
valori moștenite ale proiectului și/sau tabelul citat separat; nu sunt un tabel
tisular furnizat de GNM Head. Înlocuim formularea cu identificatorii reali ai
surselor și păstrăm marcajele legacy.

### 4.6 Compatibilitate și rapoarte deterministe

`report.py` conține timestamp-uri, căi absolute și hash-ul raportului TXT, care
include și el timpul generării. Eliminarea doar a `generated_utc` nu face JSON-ul
byte-identic. Recordul canonic trebuie să separe parametrii/rezultatele stabile
de contextul de execuție și de artefactele cu timestamp. Păstrăm hash-urile
fișierelor efective într-un manifest de rulare separat.

## 5. Corecții necesare în specificație

### Incertitudine și ponderare

- Înlocuiește „Real uncertainty” cu „analiză de sensibilitate și, unde există
  intrări și calibrare adecvate, estimare a incertitudinii”. Un ansamblu obținut
  prin perturbări ipotetice nu este automat un posterior sau interval predictiv.
- `sigma_place=null` nu trebuie înlocuit automat cu un număr inventat.
  Raportează componenta neevaluată sau cere explicit parametrul pentru un scenariu
  exploratoriu. Incertitudinea totală rămâne necunoscută.
- O normală trunchiată construită din medie/SD este o ipoteză de distribuție,
  care trebuie declarată. Media distribuției trunchiate nu mai este în general
  parametrul μ al normalei netrunchiate.
- Perturbă punctul osos și reconstruiește ținta împreună cu direcția și grosimea;
  nu perturba simultan două reprezentări dependente ale aceleiași observații fără
  un model de dependență. Distanțele derivate din markeri nu sunt date independente.
- SD a grosimii pe o direcție nu este automat eroare izotropă în trei coordonate.
  Contractul trebuie să distingă variația interindividuală, eroarea de măsurare,
  eroarea de plasare și influența manuală.
- `1/SD²` schimbă scara termenului de date și interpretarea lambda. Definim
  unitățile și normalizarea; nu multiplicăm arbitrar greutățile existente.
- Pentru comparația analitică, folosește un subcaz liniar gaussian: pose,
  corespondențe, ponderi și lambda fixe, fără Huber adaptiv/clip/TPS. Covarianța
  posteriorului nu este în general covarianța estimatorilor ridge refăcuți pe
  date perturbate. Trebuie ales și testat același obiect statistic în ambele căi.
- În loc de „95% SD”, definește exact dispersia coordonatelor, variația normală,
  intervalele percentile și incertitudinea estimării acestora. Nu promite că
  toate variantele farthest-point sunt în ±1 SD; criteriul propus nu garantează asta.
- Calibrarea nu se validează pe aceleași cazuri folosite pentru ajustarea ei.
  Două sau trei cazuri pot servi explorării, nu unei garanții de acoperire.

### Geometrie și verificări

- Distanța semnată volumetrică presupune interior/exterior bine definite.
  Pentru fragmente deschise, folosim distanță nesemnată, clearance local orientat
  pe normale verificate și stări `not_assessed`/`indeterminate` lângă limite.
  Simplul fapt de a exclude orificii prin vertex groups nu repară topologia.
  Referință tehnică: Open3D, Distance Queries, secțiunea Signed distance.
- „Os fără piele în toleranță” măsoară acoperirea într-o regiune și la o scară
  specificate; nu este echivalent cu pătrunderea osului prin piele. Raportează
  separat lipsa acoperirii, penetrarea și distanța mare.
- O fracție de vertecși depinde de densitatea triangulației. Pentru mesh-uri
  arbitrare trebuie metrici ponderate cu aria sau eșantionare uniformă pe arie,
  plus numitorul/ROI și procentul de suprafață neevaluată.
- Lipsa osului observat nu este o eroare geometrică a feței. Scalp, față, orbite,
  mandibulă și marginile fragmentelor trebuie tratate explicit.
- Eliminarea a 100% din penetrări prin proiecție la cel mai apropiat punct nu
  poate fi promisă general. O corecție poate introduce alte contacte sau afecta
  reperele. Cerem reverificare, limite de deplasare și revenire la original.
- Semaforul are nevoie și de o stare „neevaluat”, nu doar verde/galben/roșu.
  Fără prag/sursă/configurație aplicabilă nu se afișează automat verde.

### Metode, arhitectură și compatibilitate

- B1 trebuie să reproducă **implementarea actuală −r, degree=1, smoothing=0**,
  nu să reintroducă implicit kernelul 2D `r² log(r)`. SciPy documentează cele două
  kerneluri ca opțiuni distincte. Începe cu paritate numerică și evaluare pe loturi,
  apoi operatorul Blender și reverificarea QC. Păstrează CLI pentru loturi și
  calcule lungi. În Blender, lipsa SciPy nu elimină riscul blocării interfeței.
- „NumPy only în Blender” privește dependențele numerice externe; `bpy`,
  `mathutils`, `bmesh` și biblioteca standard sunt necesare adaptoarelor.
  Codul actual nu creează thread-uri de fit; comentariile vechi despre worker nu
  justifică reintroducerea lor fără o arhitectură sigură.
- A4.7 se bazează pe `identity_names` și hash-ul modelului. Specifică dacă
  componentele inactive sunt zero sau media priorului. Raportează componentele
  active și saturația separat; nu pretinde îmbunătățire anatomică înaintea evaluării.
- Stabilește explicit convențiile geometrice pentru Frankfort, semnul unghiurilor,
  definiția facial angle și alegerea Orbitale bilateral/unilateral. „Vertical”
  și „sagittal” nu definesc singure un vector complet de aplicare a grosimii.
- Nu dubla reperele existente. Distinge punctul osos, omologul cutanat, aliasul
  anatomic și rolul de referință. Identificatorii vechi rămân lizibili.
- Table selection trebuie să păstreze prioritățile: măsurare individuală/CT,
  editare manuală și tabel de referință. Nu suprascriem silențios valori pe caz.
- Atributele per-față B5 cer un format care le păstrează; STL nu transportă
  această proveniență. Pentru export este necesar un sidecar cu topologie/hash
  sau un format suportat explicit. Nu deducem proveniența din numele fișierului.
- Reducerea ponderii / creșterea σ pentru os oglindit rămân configurabile și
  necalibrate; existența marcajului de proveniență nu furnizează numeric aceste valori.
- C1 raportează descriptori și abateri configurate, nu diagnostichează automat
  craniosinostoză, modificare culturală ori pierdere dentară dintr-un scor geometric.
- `validated` în registrul de reguli trebuie separat în: formula verificată în
  sursă, implementare testată și aplicabilitate/validare externă. Confirmarea unui
  PDF nu este validare pe populația sau cazul utilizatorului.
- Compatibilitatea bit-identică se cere pentru mediul numeric fixat. Între
  platforme/BLAS se folosesc toleranțe numerice declarate. Bugfix-urile pentru
  inputuri invalide nu trebuie oprite doar pentru a reproduce o eroare veche.

## 6. Plan revizuit: maximum zece loturi, cu PR-uri separate pe task

1. **Audit, regresii și corecții de trasabilitate.** Folosește revizia V19 drept
   baseline, testele curente și fixture-uri sintetice. Corectează sursa goală,
   identificarea lambda, exportul CSV și atribuirea greșită a grosimilor.
2. **Subspațiul de identitate head-only.** Opțiune comună live/CLI, implicit `all`;
   cele 83 de componente inactive sunt fixate prin politică explicită. Teste de
   invariabilitate, prior și clip; output complet de 253 de coeficienți.
3. **Tabele tisulare versionate.** Schemas/loader și migrare exactă a datelor
   existente, proveniență per valoare, priorități pentru editările pe caz;
   apoi comparație de tabele și ponderare SD opțională cu unități definite.
4. **Cadru anatomic și repere distincte lipsă.** Frankfort/mediosagital,
   validări de degenerare, roluri separate os/piele/referință; teste pe transformări
   cunoscute. Nicio clasificare fără praguri furnizate și documentate.
5. **QC unificat și exporturi explicite.** Extinde `quality.py`; contract comun
   pass/warn/block/not_assessed, acoperire versus penetrare, metode pentru fragmente,
   rapoarte de diagnostic și export științific/ilustrativ separat.
6. **Finalizare locală NumPy în Blender.** Paritate cu spline-ul actual, aceleași
   centre și setări, caps și protecții, rezultat separat reversibil și QC. Măsoară
   timpul pe 700 de centre; păstrează calea externă pentru calcule lungi.
7. **Mandibulă, profil și dantură.** Instrument de articulare cu ipoteze salvate,
   contacte și distanțe; metrici geometrice descriptive; sensibilitate în intervale
   setate de operator. Activează constrângerea de profil numai separat, explicit.
8. **Record canonic și audit al priorului.** Extinde schema de raport existentă;
   separă timestamp-urile, introdu justificarea și diferența față de priorul neutru,
   vârsta ca metadată/criteriu de tabel, fără a simula implicit îmbătrânirea.
9. **Sensibilitate și repetabilitate.** Sesiuni A/B, import de erori măsurate,
   Monte Carlo doar cu ipoteze explicite, benchmark și diagnostic al rulărilor
   eșuate. Domeniul/calibrarea CT rămân externe și inițial neconfigurate.
10. **Asistență de plasare și scenarii.** Atlas textual/3D când există resurse,
    propuneri opționale și revizie obligatorie, proveniență per-față. Înregistrarea
    nonrigidă și detectorii de anomalii sunt ultimele, cu metrici de calitate
    separate de orice probabilitate pretins calibrată.

Aceste loturi descriu ordinea. Nu înseamnă zece PR-uri monolitice: fiecare task
implementabil are propria ramură/PR, teste și note de migrare.

### Dependențe corectate

- Schema de record și schema tabelelor pot exista înaintea motorului de
  incertitudine, cu `not_assessed`; astfel nu blocăm A6 în așteptarea întregului A7.
- În ordinea originală, A6 apărea înainte de A7 deși depinde de A7. Corectăm asta
  separând schema A7 de completarea tuturor câmpurilor ei.
- A5 depinde de verificările geometrice și, pentru criterii anatomice, de cadrul
  A4.2. Nu declarăm M1 complet dacă folosește implicit funcții încă din M2.
- Registrul A3 nu trebuie să aștepte întregul A2. Formula cu sursă verificată poate
  produce predicție și eroarea publicată, cu aplicabilitatea declarată, fără a
  pretinde că aceasta este incertitudinea întregii aproximări.
- T0.3/coherence poate fi un adaptor peste `quality.py`, nu o a doua implementare
  independentă a acelorași teste. Similar, `record.py` nu trebuie să dubleze report.py.

## 7. Separarea validării CT de dezvoltare

Rămân la autor: comparațiile cu fețele CT, decizia asupra ROI/aliniere, evaluarea
anatomică, interpretarea clinică/antropologică și concluziile pe subiecți.

Rămân în software: exporturi consecvente în mm, păstrarea originalului, identificarea
versiunii/modelului, export de metrici și ipoteze, citirea rezultatelor externe
atunci când sunt furnizate. Nu completăm automat `validation_domain.json` și nu
aplicăm un factor de calibrare din rezultate inexistente.

T0.2 și C3 nu mai au drept criteriu de acceptare obligatoriu „agentul rulează pe
2/3 cazuri CT”. Le înlocuim, pentru dezvoltare, cu cazuri sintetice și modelul
oficial. Orice claim despre acuratețe externă rămâne separat și nevalidat.
Numerele din introducerea A1 și formulele anatomice din bibliografie nu au fost
verificate din PDF-urile primare în această analiză; nu devin constante de cod.

## 8. Definiție de finalizare revizuită

- Cerința are criterii de acceptare numerice și comportament explicit pentru
  intrări incomplete/nevalide. Nu folosește valori anatomice inventate.
- Funcțiile noi sunt opt-in; corecțiile de erori au regresii specifice și note
  despre schimbarea comportamentului invalid anterior.
- Testele Python și Blender se execută înainte/după pentru revizia concretă;
  cazurile sintetice nu sunt prezentate ca studiu pe persoane.
- Schema, CLI, UI, raportul și documentația sunt coerente; citirea CSV vechi
  rămâne disponibilă fără inventarea metadatelor lipsă.
- Paritatea se verifică la aceleași inputuri și setări, cu seed și toleranțe
  numerice documentate. Schimbarea unui model statistic/calibrări este o decizie
  distinctă de trecerea testelor.
- Originalul neutru și proveniența rămân disponibile. Operațiile asupra fișierelor
  sunt validate și publicate atomic unde este posibil.
- Raport scurt per task: fișiere, teste înainte/după, modificări de comportament,
  limite și alegeri științifice rămase neconfigurate.

## 9. Primul task implementat după audit: proveniență și raportarea lambda

Ramură: `fix/provenance-lambda-audit`. Nu modifică solverul, valorile tisulare,
setările implicite sau fișierul GNM. Nu schimbă comportamentul intenționat al
`require_qc` și nu implementează încă exportul CSV atomic.

- `cranio/validation.py`: validator comun pentru prezența sursei tisulare.
  Respinge spații, valori non-text și placeholder-ele rezervate indiferent de
  capitalizare; nu pretinde verificarea științifică a textului furnizat.
- `cranio/pipeline.py`, `cranio/protocol.py`, `cranio/craniometry.py`: folosesc
  aceeași regulă. Modul strict/protocolul resping sursa invalidă; rularea obișnuită
  păstrează textul original și avertismentul.
- `cranio/report.py`: distinge lambda fixă, adaptivă și LOO. Pentru modul adaptiv
  include numărul de markeri efectiv folosiți, numărul de referință și parametrii
  base/min/max. Nu modifică selecția lambda în solver.
- `tests/test_pipeline.py`, `tests/test_provenance.py`: regresii pentru surse
  mascate prin spații/capitalizare, valori JSON nevalide, păstrarea sursei brute,
  raportul adaptiv după excluderi și paritatea OBJ cu lambda fixă echivalentă.
- `README.md`, `CHANGELOG.md` și acest document: comportament și limite explicate.

Teste înainte: **211 passed, 1 skipped**; după: **216 passed, 1 skipped**.
Testul omis necesită Windows nativ. Ruff și suita Blender 4.5.0 Linux au trecut
înainte și după; ZIP-ul a fost reconstruit și instalat în Blender la verificare.
Nu s-au rulat cazuri CT și nu s-a verificat interactiv stația Windows a autorului.

Abatere de la TASKS.md: baza V19 înlocuiește V13.5; acestea sunt bugfix-uri de
trasabilitate, nu funcții anatomice noi. Nu necesită alegerea unui tabel tisular
sau a unui prag științific. Celelalte funcții rămân în planul de dezvoltare.

## Referințe tehnice consultate

- Codul proiectului la commit-ul indicat, modelul oficial verificat prin hash,
  suitele actuale și documentația din repository.
- SciPy RBFInterpolator: https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.RBFInterpolator.html
- Open3D Distance Queries: https://www.open3d.org/docs/release/tutorial/geometry/distance_queries.html

Referințele tehnice de mai sus clarifică implementarea interpolării și semnul
distanțelor; nu validează anatomic aproximările faciale și nu introduc o nouă
dependență Open3D în proiect.
