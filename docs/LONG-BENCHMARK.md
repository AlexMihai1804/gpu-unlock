> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Testul lung pregătit pentru M6501RM

**Cea mai recentă rulare a trecut complet**, după restartul utilizatorului și alegerea Performance: `results/long-current-state-20261026-115633/`. 1.202,503 secunde totale, 1.106,597 secunde CUDA, 41.600 GEMM, 416 rezultate complete corecte. Mediane FP16/BF16: 40,705/41,887 TFLOPS. Maxim 85°C; Power Cap raportat în 98,33% din eșantioanele active, limitare termică 0%. Fără prag artificial și fără pauze termice. [Raportul final](../results/long-current-state-20261026-115633/REPORT.md). Rezultatele oprite de mai jos sunt istorice.

Stare la 26 octombrie 2026: **executat fără restart, oprit termic; 20 de minute necompletate**. Prima sarcină continuă, `results/long-current-state-20261026-110929/`, s-a oprit la 82°C după 99,516 secunde. Rularea cu pauze, `results/long-current-state-20261026-111558/`, s-a oprit la același prag după 988,129 secunde (16 min 28 s), dintre care 447,227 secunde timp CUDA. 337 blocuri, 8.425 GEMM, toate verificările numerice trecute; zero evenimente hardware noi în timpul sarcinii. Cinci avertismente corectate pe portul GPU existau anterior testului. [Raportul efectiv](../results/long-current-state-20261026-111558/REPORT.md). Imaginea UEFI instalată nu a fost schimbată.

## Varianta fără restart

**Actualizare după test:** la cererea utilizatorului, pragul artificial de temperatură este dezactivat implicit în runner și ambele launchere. Temperatura rămâne monitorizată, iar protecțiile driverului/GPU-ului nu sunt modificate. Nu s-a pornit alt test. Rulările istorice de mai sus au folosit pragul de 82°C și își păstrează rezultatele originale. Pauzele `-ThermalPacing` sunt doar o opțiune explicită, dezactivată implicit. Descrierea pragului de mai jos documentează metoda folosită în testele deja executate.

`scripts/Start-CurrentStateLongBenchmark.ps1` rulează direct în Windows curent, fără UAC, după verificarea numerică inițială. Nu modifică configurația și nu încearcă reaplicarea deblocării. Starea Secure Boot este citită din registrul Windows înainte și după; dovezile firmware/MOK anterioare rămân verificări la momentul colectării lor.

Sarcina de 20 de minute și limitele de oprire sunt aceleași ca mai jos. `bench/report_endurance.py --current-state` raportează separat verdictul de stabilitate și prezența profilului de performanță deblocat. Lipsa sporului nu împiedică testarea stabilității sesiunii actuale. Această variantă produce `launch.json`, `health-before/`, `before.json`, `endurance/`, `after.json`, `health-after/`, `review.json` și `REPORT.md`; nu produce exporturi noi de firmware sau `review-boot.json`.

Opțiunea `-ThermalPacing` folosește blocuri de 25 GEMM, pauză de la 79°C și reluare la 74°C. Pragul de oprire rămâne 82°C. Cele 1.200 de secunde includ pauzele; timpul CUDA efectiv, numărul/durata pauzelor și proporția de sarcină sunt raportate explicit. Se cere minimum 25% timp CUDA total și 10% pentru fiecare mod; aceasta este o rulare cu pauze și nu dovedește susținerea sarcinii continue. `-ReferenceRun` poate reutiliza benchmarkul scurt verificat din aceeași pornire, păstrând sursa în `launch.json`.

## Varianta cu verificarea pornirii automate și metoda comună

`scripts/Start-LongBenchmark.ps1` citește și verifică logurile interne, toate cele 19 fișiere instalate, SecureBoot/SetupMode, MOK, cheile platformei și intrările de boot. UAC este folosit numai pentru acest colector. G: este montat temporar și eliminat după citire.

Urmează benchmarkul scurt original, în toate cele patru moduri, cu aceleași biblioteci, intrări și configurație ca referința. Sarcina lungă cu verificarea deblocării cere ieșiri complete identice și randament pe frecvența SM consistent cu B2, aproximativ dublu față de referința normală pentru FP16/BF16, cu controale TF32/FP32 apropiate de referință. Se folosesc minimum cinci eșantioane active pe mod; lipsa lor produce un verdict neconcludent. Pragul vechi FP16/TF32 >2,5 a fost înlocuit fiindcă poate respinge greșit starea deblocată la 80 W. Normalizarea grosieră nu înlocuiește citirea directă a selectorilor în Windows.

`bench/endurance.py` rulează **1.200 de secunde** de sarcină alternativă FP16/BF16 pe matrice 8192×8192 păstrate în memoria GPU. Acumulare/ieșire FP32, cuBLAS math mode 16, cuantizare și seed 3060 ca referința. După fiecare bloc de 100 GEMM verifică toate valorile finite, hashul întregii ieșiri față de referință și 2.048 de elemente față de CPU FP64, eroare relativă L2 sub 0,0001.

Cronometrarea CUDA exclude copierea și validarea. Se cer minimum 70% timp CUDA măsurat și minimum 30% din durata țintă pentru fiecare mod. Pregătirea și benchmarkurile scurte înainte/după adaugă câteva minute duratei totale.

La final, benchmarkul scurt și verificările de sănătate trebuie să confirme păstrarea performanței și corectitudinii. Nu schimbă driverul, puterea, frecvențele, firmware-ul, cheile sau configurația de boot. Cere temporar Windows să evite sleep-ul automat; cererea este eliminată la ieșire și nu blochează suspendarea manuală.

## Monitorizare și oprire

Telemetrie aproximativ o dată pe secundă: temperatură GPU, putere, frecvențe SM/memorie, utilizare, VRAM, P-state, motive de limitare și alimentare AC. Evenimentele Display/nvlddmkm/WHEA și intrările în sleep/Modern Standby sunt verificate la aproximativ 25 de secunde.

Oprire la temperatură GPU ≥82°C, alimentare deconectată/necunoscută, eroare CUDA/cuBLAS/numerică, eveniment driver/hardware neașteptat, sleep sau pierderea monitorizării. **82°C este pragul ales pentru test**, nu limita oficială a GPU-ului. WHEA 17 corectat, AMD 1022:14ba la 00:02.1, cu stare necorectabilă zero, este avertismentul de rețea observat anterior; rămâne în log, separat de erorile neașteptate.

Ctrl+C sau fișierul gol `STOP` în folderul `endurance` opresc sarcina la următorul punct de verificare. Răspunsul nu este instantaneu în timpul apelurilor CUDA/interogărilor de sistem.

## Rezultate

Fiecare rulare creează `results/long-benchmark-<data-ora>/`; calea este în `results/latest-long-benchmark.txt`.

| Fișier | Conținut |
|---|---|
| `automatic-boot/` | Loguri preboot, hashuri instalate, Secure Boot și variabile de boot citite |
| `review-boot.json`, `review-before.json`, `review-after.json` | Verificările etapelor, păstrate separat |
| `before.json`, `after.json` | Benchmarkuri scurte cu aceleași biblioteci, configurație și intrări |
| `endurance/blocks.jsonl` | Cronometrare și verificări numerice pentru fiecare bloc |
| `endurance/telemetry.jsonl`, `endurance/health.jsonl` | Telemetrie și evenimente |
| `endurance/progress.json`, `endurance/summary.json` | Progres și rezultat efectiv |
| `review.json`, `REPORT.md` | Verdict și rezumat după rularea completă |

Un PASS acoperă această sarcină cu intrări fixe și această pornire. Hashurile verifică ultima înmulțire din fiecare bloc, nu toate rezultatele intermediare. Nu certifică toate aplicațiile, erorile rare sau persistența după sleep/resume. Diferențele de putere/frecvență trebuie interpretate din telemetrie; procentul față de referința istorică nu izolează automat efectul deblocării.

Verificările offline se rulează cu `.\.venv\Scripts\python.exe -X utf8 bench\test_endurance.py -v`. Cele șapte teste verifică pragul termic, histerezisul răcirii, alimentarea, filtrarea evenimentelor, telemetria și sumarizarea. Nu înlocuiesc rularea fizică a runnerului lung.
