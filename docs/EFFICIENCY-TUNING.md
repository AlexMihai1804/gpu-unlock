> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Măsurarea eficienței și testarea temporară a curbei

Actualizare ulterioară: [runda adaptivă până la +120 MHz a trecut](ADAPTIVE-TUNING.md), inclusiv validarea de 10 minute CUDA a candidatului +120 MHz. Aceasta este concluzia cea mai recentă; testul +60 descris mai jos rămâne dovada etapei inițiale.

Actualizare după acceptarea UAC: [testul temporar a trecut](../results/efficiency-trial-20261026-131407/CONCLUSION.md). +60 MHz a adus un câștig observat de eficiență de +2,65% FP16 / +2,38% BF16 față de referințele vecine. Au fost măsurate 8.000 de GEMM-uri în 20 de blocuri cu verificare integrală a ieșirii finale, fără erori noi, cu maxim 83°C. Offseturile inițiale au fost restaurate și verificate independent. +60 MHz rămâne un candidat pentru testare lungă; nu s-a aplicat un profil permanent. Restaurarea normală a fost validată pe hardware; intervenția watchdog-ului la blocare nu a fost provocată.

Referința anterioară, de mai jos, păstrează istoricul primei încercări UAC anulate.

Referința măsurată este în [EFFICIENCY-REPORT.md](../results/efficiency-20261026-123610/EFFICIENCY-REPORT.md): FP16 0,3633 TFLOP/J, BF16 0,3721 TFLOP/J. Au fost măsurate 1.600 de GEMM-uri, în patru blocuri cu verificare integrală a ieșirii finale. Acesta este un test scurt la setările existente. Cererea UAC pentru reglaj a fost anulată; +30/+60 MHz nu au fost aplicate. Calea de reglaj și watchdog-ul au verificări automate, dar nu au fost încă validate pe hardware printr-un reglaj efectiv.

Se folosesc NVIDIA NVML din Windows și aceleași biblioteci CUDA/cuBLAS și intrări ca în testul lung validat. Nu se instalează un utilitar de overclock și nu se modifică firmware-ul sau pornirea automată existentă.

## Ce s-a verificat pe laptop

- API-ul vechi `nvmlDeviceGetGpcClkVfOffset` răspunde `NOT_SUPPORTED`.
- API-ul nou `nvmlDeviceGetClockOffsets` funcționează și raportează inițial 0 MHz pentru GPU și VRAM.
- `nvmlDeviceGetTotalEnergyConsumption` funcționează. Diferența contorului măsoară energia GPU în mJ, permițând lucrul pe joule în fereastra măsurată.
- `nvmlDeviceGetThermalSettings` expune un senzor cu ținta GPU. Nu s-a găsit un senzor separat pentru VRAM/hotspot prin această interfață.
- Citirea privată NVAPI `GetVFPCurve` funcționează. Se salvează răspunsul binar, JSON și CSV; parserul validează domeniile și ordinea tensiunilor. Sunt capturate primele 80 de puncte, fără garanția curbei complete.

Surse pentru ABI: [antetul oficial NVIDIA NVML](https://github.com/NVIDIA/go-nvml/blob/main/pkg/nvml/nvml.h), [structura NVAPI numai pentru citire](https://github.com/falahati/NvAPIWrapper/blob/2a41eb4d6b1bceff5dbb33a3b5ea70bd582214a7/NvAPIWrapper/Native/GPU/Structures/PrivateVFPCurveV1.cs). Exportul NVAPI este o interfață privată și poate necesita adaptare la alte drivere.

## Măsurare fără reglaj

Într-un director nou `results/efficiency-...`, creați mai întâi referința:

```powershell
.\.venv\Scripts\python.exe bench/gemm.py --output results/efficiency-EXEMPLU/before.json --label efficiency-reference
.\.venv\Scripts\python.exe bench/efficiency.py --output-directory results/efficiency-EXEMPLU
.\.venv\Scripts\python.exe bench/report_efficiency.py results/efficiency-EXEMPLU
```

Prima comandă creează directorul. Măsurarea implicită nu schimbă setări. `--inventory-only` salvează numai senzorii și curba. `before.json` trebuie să confirme profilul deblocat prin verificările existente.

## Testul temporar cu offset

Opțiunea explicită `--trial` testează secvența 0 / +30 / 0 / +60 / 0 MHz prin API-ul public `nvmlDeviceSetClockOffsets`. Necesită administrator. Limitele numerice acceptate de API nu sunt o validare a stabilității; testul este limitat în cod la 0, +30 și +60 MHz.

Nu se aplică o tensiune fixă și nu se crește limita de putere. Nu se scriu offseturi VRAM. Un offset pozitiv poate fi descris ca overclock la aceeași tensiune; nu trebuie numit automat undervolt validat.

Lansatorul creează un director nou, generează o referință proaspătă în toate cele patru moduri, apoi rulează experimentul și raportul. Cere UAC dacă terminalul nu este deja administrator:

```powershell
powershell.exe -NoProfile -File ".\scripts\Start-EfficiencyTrial.ps1"
```

Nu relansați măsurarea în directorul rezultatului vechi. `--trial` nu este un profil persistent; reglajul +60 MHz nu are încă validare lungă. La reluarea reglajului se verifică întâi codul și că există o pornire cu unlock confirmat.

Testul refuză offseturi inițiale nenule, verifică citirea după fiecare reglaj și restaurează setarea inițială în `finally`. Un proces separat verifică restaurarea și încearcă revenirea la zero dacă procesul principal dispare sau nu mai actualizează heartbeat-ul timp de 50 secunde. Restaurarea software nu poate fi garantată în cazul blocării întregului sistem.

Se pot opri măsurările prin crearea fișierului `STOP` în directorul testului. Oprirea este verificată între blocuri. Se verifică alimentarea la priză, jurnalul driverului/hardware-ului și fiecare ieșire finală de bloc, integral, față de SHA256 inițial și 2.048 de valori CPU FP64. Nu există prag artificial de temperatură.

Fiecare fereastră de aproximativ 10 secunde este încadrată de citirile energiei. Verificarea CPU și transferul final sunt în afara ferestrei. Energia include întreaga activitate GPU din interval, inclusiv alte aplicații. Contorul este comparat cu puterea din telemetrie pentru a respinge rezultate inconsistente.

Rezultatele scurte identifică doar candidați pentru testare lungă. Nu se creează un profil de reglaj aplicat la pornire. Un câștig se compară cu ambele referințe vecine și se interpretează împreună cu puterea, temperatura, tensiunea și frecvența efectivă.
