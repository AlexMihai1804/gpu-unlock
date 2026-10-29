> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Unlock validat în testul complet de 20 de minute, în Performance

**Actualizare ulterioară: FP16/BF16/TF32 sunt validate fizic în noua pornire.** Hashul MOK nou este înrolat, Secure Boot este activ, iar logul confirmă SS0=0x88888888 și SS1=8 după un FLR. TF32 a crescut la **23,467 TFLOPS** în benchmarkul scurt (+69,25% față de stock), cu **22,551 TFLOPS mediană** în testul de 5 minute. Ordinea implicită a fost verificată prin readback ca Boot0006 → Boot0000 → Boot0001; persistența acestei ordini după încă o repornire nu a fost testată. Vezi [instrucțiunile curente](START-TF32-AUTOMATIC.md) și [raportul nou](../results/automatic-tf32-physical-20261026-193847/REPORT.md). Rezultatele FP16/BF16 de mai jos rămân istorice și neschimbate.

**Rezultat 26 octombrie 2026: PASS.** Utilizatorul a repornit laptopul, apoi a selectat Performance și a cerut reluarea de la zero. Rularea `results/long-current-state-20261026-115633/` a completat **20 min 2,5 s**, fără prag artificial de temperatură și fără pauze termice impuse. Timpul CUDA măsurat a fost 18 min 26,6 s, adică 92,0% din durată; restul reprezintă verificări și transferuri.

Noul log `RUN0001` confirmă deblocarea automată; Secure Boot, MOK și fișierele instalate au trecut verificarea. Benchmarkul inițial: **42,419 TFLOPS FP16 / 43,774 BF16**; după test: **42,342 / 43,727**, sub 0,2% diferență. În sarcina lungă, medianele blocurilor active sunt **40,705 / 41,887 TFLOPS**. Toate cele 416 rezultate complete verificate, după 41.600 GEMM, sunt corecte; zero erori Display/nvlddmkm/WHEA în această pornire la verificarea finală.

**Limitarea dominantă este puterea:** SW Power Cap în **98,33%** dintre cele 1.020 de eșantioane active. Limita curentă observată în snapshoturi a variat între **110,80 și 117,93 W**, mediană 113,29 W, după ce profilul anterior oferea circa 80 W. Temperatura maximă: **85°C**; SW/HW Thermal Slowdown și HW Power Brake: **0%** din eșantioanele active. Procentele sunt observații de telemetrie, nu atribuirea exactă a timpului CUDA.

[Raportul complet](../results/long-current-state-20261026-115633/REPORT.md) și [datele/verificările JSON](../results/long-current-state-20261026-115633/review.json). Unlock-ul și performanța sunt validate pentru această pornire și sarcină. Păstrarea după idle/sleep este o problemă separată; [investigația](PERSISTENCE-INVESTIGATION.md) delimitează dovezile și ce rămâne neconfirmat. Nu este programată altă rulare sau repornire.

Un prag fix bazat numai pe TFLOPS nu este suficient la puteri diferite. În noul boot, înainte de Performance, FP16 avea 27,185 TFLOPS la 915 MHz, adică randament pe frecvență apropiat de cel deblocat. După standby în bootul anterior avea 22,622 TFLOPS la 1.507 MHz, apropiat de cel normal. Evaluarea folosește acum și telemetria SM; nu citește direct selectorii în Windows.

## Istoricul testelor din bootul anterior

În `RUN0000`, pornirea internă a executat deblocarea fără USB și fără tasta U: SS0=0x88888888, SS1=0x3 păstrat, un FLR, zero mapări DMA rămase, atribute PCI restaurate înainte de Windows. Imaginea instalată coincide cu cea aprobată.

Verificarea din **26 octombrie 2026** confirmă SecureBoot=1, SetupMode=0, validare shim activă, noul hash MOK înrolat și cele patru hashuri vechi păstrate. PK/KEK/db/dbx și Windows Boot Manager sunt identice cu referințele. BootCurrent=0000; BootOrder începe cu 0000,0001, urmate de alte intrări listate de firmware.

După **Modern Standby** peste noapte, benchmarkul a măsurat **22,622 TFLOPS FP16 / 23,233 BF16**. Toate verificările numerice și hashurile complete au trecut, dar lipsește profilul de performanță deblocat (~43–44 TFLOPS anterior). Limita de putere raportată este acum 80 W; condițiile diferă de cele anterioare. Pierderea efectului după standby este o explicație posibilă; selectorii nu au fost citiți în Windows și cauza exactă nu este demonstrată.

**Testul a fost executat fără restart.** Încercarea continuă s-a oprit la 82°C după 99,516 secunde. Rularea următoare cu pauze termice s-a oprit la același prag după **16 min 28 s**, cu **7 min 27 s timp CUDA efectiv**. Cele 20 de minute planificate nu au fost completate și nu se acordă PASS pentru durata completă.

În rularea lungă: FP16 **21,807 TFLOPS**, BF16 **22,358 TFLOPS**, mediane ale blocurilor active. **8.425 GEMM**, 337 rezultate complete verificate; toate verificările numerice au trecut. Nu au apărut erori Display/nvlddmkm sau evenimente hardware noi în timpul testului. Existau însă **cinci avertismente PCIe corectate pe portul GPU înaintea testului**, distincte de avertismentul vechi de rețea; cauza lor nu este stabilită.

[Raportul rezultatului efectiv](../results/long-current-state-20261026-111558/REPORT.md) include datele brute, timpul în pauze și limitele interpretării. Sporul de performanță deblocat nu este confirmat în această sesiune de după standby. Nu s-a schimbat imaginea UEFI, limita de putere, driverul sau configurația de boot. Nu este programată altă rulare sau repornire. Înrolarea MOK este terminată și nu trebuie repetată.

Pentru aceeași metodă fără restart se folosește `scripts/Start-CurrentStateLongBenchmark.ps1`. Această variantă nu cere UAC și nu reexportă variabilele firmware; citește starea Secure Boot din Windows, rulează benchmarkurile și monitorizează GPU-ul/evenimentele. Nu are condiția unui profil de performanță deblocat, dar îl raportează separat. Calea ultimei rulări este în `results/latest-long-benchmark.txt`.

## Variantă opțională pentru o pornire nouă, mai târziu

1. Salvează lucrul, conectează alimentatorul și alege **Restart** din Windows. Lasă pornirea normală, fără USB și fără Esc.
2. După desktop, păstrează capacul deschis și evită sleep/restart. Scrie **„gata pentru testul lung”**; agentul poate porni testul și urmări rezultatele.
3. Pentru pornire manuală, din PowerShell obișnuit:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\Projects\gpu-unlock\scripts\Start-LongBenchmark.ps1'
```

Acceptă cererea UAC pentru citirea logului intern și a variabilelor Secure Boot. Montarea temporară G: este eliminată după citire. Testul nu modifică driverul, frecvențele, limita de putere, firmware-ul, cheile sau configurația de boot.

Benchmarkul scurt trebuie să confirme performanța deblocată înainte de sarcina de 20 de minute. Pregătirea și verificările adaugă câteva minute duratei totale. Pragul de temperatură al scriptului este dezactivat implicit, conform cererii utilizatorului; protecțiile driverului și GPU-ului rămân active. Oprire la pierderea alimentării, erori numerice/driver/hardware, sleep sau pierderea monitorizării. Ctrl+C ori fișierul gol `STOP` în folderul `endurance` opresc sarcina la următorul punct de verificare.

Rezultatele se salvează în directoare noi `results/long-benchmark-<data-ora>/`. Calea ultimei rulări este în `results/latest-long-benchmark.txt`. `REPORT.md` și `review.json` sunt generate după rularea completă. [Metoda și limitele testului](LONG-BENCHMARK.md).

## Instalare și recuperare

Noua partiție FAT32 **M6501GPU**, 512 MiB, este discul 1, partiția 4, GUID `33333333-3333-4333-8333-333333333333`. E: a fost redus cu acord de la 100 la 99,5 GiB. Intrarea internă folosește `\EFI\M6501GPU\shimx64.efi`; Windows Boot Manager original este imediat după ea. Nu s-a făcut flash BIOS/VBIOS sau înlocuire de loader Windows.

În cele 5 secunde ale aplicației, **Esc** anulează deblocarea și pornește Windows normal. Meniul temporar ASUS Esc permite alegerea Windows Boot Manager original. La STOP sau lipsă persistentă de progres, oprește complet laptopul și folosește Windows Boot Manager la pornirea următoare.

Pentru dezactivare, dintr-un PowerShell nou ca Administrator:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\Projects\gpu-unlock\scripts\Disable-InternalAutomatic.ps1' -InstallDirectory 'C:\Projects\gpu-unlock\results\internal-install-20261025-223906'
```

Scriptul restaurează ordinea salvată numai dacă starea actuală corespunde verificărilor sale; poate refuza după adăugarea altor intrări de către firmware. Nu șterge partiția, nu extinde E: și nu elimină MOK/cheile platformei.

Hash MOK: `433c71743989ae1ad24dff7bf9b47052270d3f85778f750226cb787531d5ae93`. SHA-256 al executabilului: `07a4e62f680122b9c2291729f41e3d92045f87dafb262ba7bad619eb3f6542e6`. Nu înlocui imaginea instalată fără verificarea unui nou hash.

Dovezi: `results/automatic-physical-20261026-072038/`, `results/automatic-before-endurance-2026-10-26.json`, respectiv istoricul instalării `results/internal-install-20261025-223906/`.
