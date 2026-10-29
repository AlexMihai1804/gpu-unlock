> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Testul adaptiv +60 / +90 / +120 MHz

Runda ulterioară [de comparație +120 / +150 MHz a trecut](../results/compare150-tuning-20261026-181115/CONCLUSION.md). +150 a adus aproximativ 1% debit brut și +1,07% FP16 / +1,64% BF16 eficiență marginală normalizată față de +120 în etapa comparativă. Validarea +150 a acumulat 601,25 secunde CUDA, cu toate verificările corecte, dar și o derivă de −1,10% FP16 / −0,77% BF16 și două eșantioane HW Thermal Slowdown. Maxima validării +150 a fost 86°C; controlul final la 0 MHz a ajuns la 87°C. Offseturile inițiale au fost restaurate; repausul final a fost P8 la circa 12 W. Nu s-a aplicat un profil permanent.

Runda din 26 octombrie a trecut: [concluzie și date](../results/adaptive-tuning-20261026-163227/CONCLUSION.md). +120 MHz a fost cel mai bun candidat, validat cu 605,7 secunde CUDA și cu aproximativ +5,75% eficiență FP16 / +4,89% BF16 față de controalele vecine la 0 MHz, la circa 119 W. Toate cele 166 de verificări ale ieșirilor finale de bloc au trecut. Maxima întregii telemetrii a fost 86°C; validarea lungă a avut trei eșantioane SW Thermal Slowdown (0,10%), față de 99,90% SW Power Cap. Offseturile inițiale au fost restaurate și verificate independent. Nu există profil suplimentar aplicat automat.

Scop: evaluarea câștigului de debit și TFLOP/J pe M6501RM, cu limita de putere existentă și fără un profil suplimentar aplicat la pornire. Creșterea până la +90 sau mai mult a fost cerută de utilizator. Limita acestei runde este +120 MHz.

## Comparația ulterioară cu +150 MHz

După solicitarea utilizatorului privind +150 MHz s-a adăugat un plan separat, explicit:

```powershell
powershell.exe -NoProfile -File ".\scripts\Start-AdaptiveTuning.ps1" -Plan Compare150
```

Acesta testează numai +120 și +150 MHz, fiecare între controale la 0 MHz, apoi validează candidatul selectat timp de 600 secunde CUDA. Nu repetă etapele +60/+90. În acest plan limita este +150 MHz; planul implicit rămâne limitat la +120 MHz. Configurațiile arbitrare ale listei de offseturi sunt refuzate. Rezultatul este indicat de `results/latest-150-tuning.txt`.

La pregătirea comparației, driverul raporta deja P0 și aproximativ 27 W la repaus, cu offseturile restaurate din runda anterioară. Noul plan salvează separat `idle-before.csv`. Această observație nu stabilește cauza stării P0 și nu permite atribuirea ei unui offset +150 care încă nu fusese aplicat.

Lansare din directorul proiectului:

```powershell
powershell.exe -NoProfile -File ".\scripts\Start-AdaptiveTuning.ps1"
```

Lansatorul cere UAC, creează un director nou `results/adaptive-tuning-...`, arhivează codul executat și generează un benchmark de control proaspăt. Testul refuză un control care nu confirmă performanța deblocată sau offseturi inițiale nenule. Calea rezultatului este în `results/latest-adaptive-tuning.txt`.

## Succesiunea

Duratele sunt timp CUDA măsurat, împărțit între FP16 și BF16, nu minute de așteptare. Fiecare bloc conține 400 de GEMM-uri, cu verificarea integrală a ieșirii finale și 2.048 de valori CPU FP64. Verificarea CPU și transferul final sunt în afara ferestrei de energie.

1. Stabilizare la 0 MHz: 180 secunde CUDA.
2. Referință la 0 MHz: 90 secunde.
3. +60 MHz: 180 secunde, urmat de o nouă referință de 90 secunde la 0 MHz.
4. +90 MHz, apoi +120 MHz, numai dacă pasul precedent este justificat: câte 120 secunde, fiecare urmat de 90 secunde la 0 MHz.
5. Cel mai bun candidat: cel puțin 600 secunde CUDA, apoi 120 secunde de control final la 0 MHz.

Fiecare pas cere pentru ambele moduri: eficiență cu peste 1% și debit cu peste 0,5% mai mari decât fiecare referință vecină, putere medie în ±3%, temperatură maximă în ±3°C, minimum trei blocuri per mod și toate verificările corecte. După +60 se cere și un câștig marginal de eficiență de peste 0,5% față de candidatul anterior, normalizat la controalele proprii. Aceste praguri sunt filtre practice, nu o analiză de semnificație statistică.

Validarea finală verifică și evoluția debitului: ultimul sfert nu trebuie să fie cu peste 3% mai slab decât primul. Un rezultat de execuție PASS nu înseamnă automat că un reglaj merită; raportul separă aceste concluzii.

## Restaurare și limite

Se scrie numai offsetul GPC prin API-ul public NVML. Nu se scriu tensiuni fixe, limite de putere, offseturi VRAM, BIOS/VBIOS, chei Secure Boot sau configurarea de boot. Protecțiile driverului rămân active. Nu există prag artificial de temperatură în aplicație.

La erori numerice, evenimente de driver/hardware, deconectarea alimentatorului sau fișierul `STOP`, testul se oprește și încearcă restaurarea offseturilor inițiale. Un proces separat verifică restaurarea și intervine dacă procesul principal dispare sau heartbeat-ul expiră după 50 secunde. Deadline-ul independent este de o oră. Blocarea întregului sistem nu permite garantarea restaurării software.

Pe durata sarcinii se inhibă suspendarea automată numai pentru firul benchmarkului, printr-un apel Windows reversibil; configurația persistentă a planului de alimentare nu este schimbată.

Progres: `progress.json`; date: `energy-blocks.jsonl`, `energy-telemetry.jsonl`, `offset-events.jsonl`; decizii: `adaptive-summary.json`. La final se verifică independent offseturile și se generează raportul prin `bench/report_adaptive_tuning.py`. Rezultatul acoperă acest GEMM și această pornire, fără certificarea tuturor aplicațiilor sau a persistenței după suspendare.
