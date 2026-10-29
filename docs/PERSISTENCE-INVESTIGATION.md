> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# De ce dispare sporul și ce îl limitează

Analiză din 26 octombrie 2026, pe baza logurilor salvate și a măsurătorilor după restart. Nu s-au schimbat firmware-ul, driverul sau cheile. Profilul Performance a fost selectat de utilizator.

## Verificarea ulterioară după Modern Standby

La verificarea de după revenirea din 26 octombrie, ora 16:21:14, profilul deblocat încă funcționa: FP16 41,952 TFLOPS la 1.417 MHz și BF16 43,301 TFLOPS la 1.447 MHz. Randamentele normalizate sunt 0,997× și 1,011× din referința deblocată; controalele TF32/FP32 corespund și ele. Pornirea Windows era tot cea de la 09:46:47 UTC, iar Secure Boot era activ. Jurnalul confirmă intrarea în Modern Standby la 14:24:13 și revenirea la 16:21:14, plus alte cicluri intermediare.

Această observație arată că un eveniment Modern Standby nu implică automat pierderea unlockului. Ea nu stabilește ce tranziție efectivă de alimentare a parcurs GPU-ul și nu invalidează pierderea observată în bootul anterior. Raportul nou este în directorul indicat de `results/latest-unlock-before-tuning.txt`, împreună cu jurnalul recent de suspendare și clasificarea normalizată. Nu s-a schimbat offsetul pentru această verificare.

## Două fenomene distincte

**Puterea disponibilă limitează frecvența chiar dacă unlock-ul funcționează.** După noul restart, înainte de Performance, FP16 a măsurat 27,185 TFLOPS la o mediană SM de 915 MHz și circa 80 W. Asta înseamnă aproximativ 29,7 TFLOPS/GHz, foarte aproape de referința deblocată B2, 29,7 TFLOPS/GHz. După schimbarea profilului de către utilizator, puterea raportată disponibilă a urcat spre 110–115 W, iar benchmarkul inițial a măsurat 42,419 FP16 / 43,774 BF16. Aceste observații sunt din aceeași pornire, fără reaplicarea deblocării între ele.

**Datele din bootul anterior, după standby, corespund unui randament pe frecvență normal.** Acolo FP16 avea 22,622 TFLOPS la 1.507 MHz, aproximativ 15,0 TFLOPS/GHz; referința normală este aproximativ 15,4. Prin urmare, limita de 80 W explică o parte din reducerea frecvenței, dar nu explică singură diferența de aproximativ două ori în randamentul FP16/BF16 pe frecvență. TF32/FP32 au randamente pe frecvență apropiate de referințe în ambele cazuri.

Normalizarea folosește telemetrie grosieră din fazele active, inclusiv warmup, nu frecvența integrată exact în intervalele evenimentelor CUDA. Ea coroborează logul de boot și benchmarkurile; **nu este o citire directă a selectorilor GPU în Windows**. Pragul vechi FP16/TF32 >2,5 a fost înlocuit în evaluare: singur poate respinge greșit un laptop deblocat, dar limitat la 80 W.

## Explicația probabilă a pierderii stării

Logurile Windows confirmă intrarea în Modern Standby la 23:05 pe 25 octombrie și revenirea prin deschiderea capacului la 07:19 pe 26 octombrie, înainte de benchmarkul redus de la 07:21. Există intervale efective DRIPS în această perioadă. Laptopul oferă S0 Low Power Idle; S3 nu este disponibil.

[Proiectul Linux](https://github.com/Zagitta/gpu-unlock/blob/af28cbbfd3d922a659227ecfb7369adfd924cf03/README.md) explică pierderea selectorilor la întreruperea alimentării și include reaplicarea înaintea reluării driverului NVIDIA. [Sursa tranzacției](https://github.com/Zagitta/gpu-unlock/blob/af28cbbfd3d922a659227ecfb7369adfd924cf03/kernel/gpu_unlock/unlock_610.c) verifică starea dispozitivului suspendat înainte de a încerca acest lucru. Aplicația noastră UEFI execută tranzacția la boot și apoi predă controlul către Windows; nu are un mecanism de reactivare la resume.

[Microsoft documentează D3cold pentru dGPU în Modern Standby](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/modern-standby-graphics). În cazul acestui laptop, **resetarea stării printr-o tranziție de alimentare rămâne explicația principală, nu o tranziție individuală demonstrată**. Nu există măsurare imediat după prima pornire automată și înainte de standby, nici un traseu istoric complet D3cold și nici citire SS0/SS1 în Windows. Idle runtime D3cold, standby sau o reinițializare a driverului nu pot fi separate definitiv din datele existente.

## Avertismentele PCIe

În bootul anterior, primul avertisment corectat pe portul GPU AMD 1022:14b8 apare la 07:59, după benchmarkul deja redus de la 07:21. Avertismentele nu demonstrează cauza pierderii sporului. Au UncorrectableErrorStatus=0, sunt distincte de avertismentul de rețea 1022:14ba și rămân în dovezi. Noul log și benchmarkul după restart nu au aceste avertismente la colectarea inițială.

## Ce poate stabili testul Performance

Rularea `results/long-current-state-20261026-115633/` a trecut complet: 20 min 2,5 s, 41.600 GEMM, toate verificările corecte, zero erori noi. Mediane 40,705 TFLOPS FP16 / 41,887 BF16. Benchmarkul final a rămas la sub 0,2% de valorile inițiale. Unlock-ul s-a menținut în sarcina continuă.

Limitarea dominantă observată a fost SW Power Cap, în 98,33% din 1.020 de eșantioane active. Temperatura maximă: 85°C, fără SW/HW Thermal Slowdown sau HW Power Brake raportat. Snapshoturile au arătat limite curente între 110,80 și 117,93 W. Telemetria separă acești indicatori conform [documentației NVIDIA](https://docs.nvidia.com/deploy/archive/R535/nvml-api/group__nvmlClocksEventReasons.html). Procentele reprezintă eșantioane active, nu atribuirea exactă a timpului CUDA. Nu s-a introdus un prag artificial de temperatură.

Stabilitatea într-o sarcină CUDA continuă nu dovedește păstrarea deblocării după idle/sleep: sarcina însăși menține GPU-ul activ. Dovezile analizei și comparațiile normalizate sunt în `results/persistence-investigation-20261026-114527/persistence-analysis.json`.
