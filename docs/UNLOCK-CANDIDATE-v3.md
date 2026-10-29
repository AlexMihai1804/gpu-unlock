> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# M6501RM v3: candidat local, neaplicat

**Pregătirea și testele locale sunt încheiate. Copierea pe stick, înrolarea noului hash MOK și o încercare fizică de unlock necesită acord distinct.** Stickul actual conține CAPTURE; acest document nu înseamnă că deblocarea a fost aplicată. Raport: `results/unlock-candidate-v3-ready.json`.

## Fișierul de revizuit

- Executabil: `build/candidate-20261025-v3/M6501-UNLOCK-CANDIDATE.EFI`.
- Pachet local: `build/release-20261025-v3/USB-CANDIDATE/`.
- SHA-256 fișier: `f716f8827c38a63b353fd28ad505bb2e7713991fb152df6b34a250c89bd08336`.
- **Hash PE/Authenticode pentru MOK:** `5dca60a7602255a01ff4f7771aacac62100afda4138f9235d0476f9b48f68642`.
- SHA-256 manifest de staging: `348e4deedfceea89e176c6dc1abe1f71b72978271e9c75fc0f3c8341e13fa31f`.
- Profil: `config/board.reviewed.json`. `evidence_reviewed=true` înseamnă revizie statică pentru construirea candidatului, **nu validare fizică a deblocării**. Profilul `board.pending.json` și executabilul blocat anterior se păstrează.

Executabilul verifică modelul și BIOS-ul ASUS exacte, PCI `2520/1313:1043` A1, chipul `0xb76000a1`, 6144 MiB și PROM-ul original:

`dce995afb0e825c9640488b55054179ebc15c77d38c00ed45a05f7e2701433e7`.

Valorile fuse trebuie să fie Booter `0x1` și FWSEC `0x3`; selecția semnăturii FWSEC trebuie acceptată înainte de armare. SS0 se citește din bootul curent, apoi ținta este `0x88888888`. **SS1 se citește în fiecare boot, nu se scrie și trebuie să rămână identic înainte/după FLR.** Valoarea capturată aici a fost 3; un istoric SS0 sau SS1 al altui laptop nu este folosit drept condiție universală.

## Dovezile și limitele

PROBE, HANDOFF și CAPTURE au trecut fizic. După CAPTURE, colectarea UAC reluată în `results/uefi-post-capture-20261025-203931/` a confirmat SecureBoot=1, SetupMode=0, validare shim activă, hashul CAPTURE în MokListRT, PK/KEK/db/dbx identice și Windows Boot Manager identic/primul. Cele trei imagini PROBE/HANDOFF/CAPTURE reconstruite în folderul v3 au exact hashurile imaginilor testate anterior.

Nucleul este fixat la `craftingmod/rtx30-unlock` commit `5c076dc4ee7fa369639669fa591ac74d8f6dfcd8`; checkoutul upstream rămâne nemodificat. Patchul generat local elimină scrierea SS1 și adaptează ambele verificări de readback. Nu este preluat executabilul unui alt laptop.

Layout-ul calculat din captura reală este `nonwpr=0x175300000`, `WPR=0x175400000`, `GSP=0x17ada0000`, `boot=0x17fdfa000`, `FRTS=0x17fe00000`, `end=0x17ff00000`. Regiunea rămâne în vârful celor 6 GB, conform calculului fixat. FWSEC provine din ROM-ul acestei plăci; Booter/GSP/V67 și descriptorul sunt cele cinci assets fixate, verificate la încărcare ca dimensiune și SHA-256.

Au trecut:

- 53 verificări ale adaptorului, 255 verificări PCI, testele transportului PCI/DMA și 48 verificări SHA-256;
- 20 scenarii ale tranzacției cu PROM sintetic și servicii UEFI simulate;
- alte 20 scenarii cu **ROM-ul original, configurația PCI capturată, profil runtime și layout-ul real de 6 GB**, cu serviciile UEFI/GPU simulate;
- 13 cazuri ale preflightului real, cu ROM original/modificat, chip greșit, fuse greșite, MSI activ, WPR activ și selectori variați; orice scriere PCI/MMIO este interzisă în acest test;
- 18 teste Python, verificarea PE/NX/SBAT/relocărilor, pachetele locale și refuzul scriptului de deployment fără aprobare.

Testul inițial pe datele capturate a expus o coliziune întâmplătoare între o adresă CPU Windows și adresa DMA inventată de simulator. Simulatorul sare acum explicit acea adresă și păstrează condiția de mapare diferită de CPU. Nu s-a relaxat nicio verificare a transportului real și nu s-a accesat GPU-ul pentru corectarea testului. Rapoartele finale sunt `build/candidate-20261025-v3/tests/report.json` și `capture-board-verified/report.json`; logurile încercărilor anterioare se păstrează pentru audit.

**Nu sunt validate:** execuția reală FWSEC/Booter/V67 pe această placă, comportamentul real DMA/IOMMU și alocările preboot, tranzacția/FLR și compatibilitatea cu driverul Windows 580.97. [Raportul primar #58](https://github.com/Zagitta/gpu-unlock/issues/58) folosește un ASUS FA506QM, alt VBIOS/subsystem, driver 610.91 și Secure Boot oprit. Valorile similare sunt context tehnic, nu o validare a acestui candidat. Cele șase teste VM existente validează lanțul și handoff-ul pentru imaginile testate acolo; nu emulează GPU-ul sau acest unlock.

## Ce schimbă prima încercare și riscuri

Această etapă depășește CAPTURE: activează temporar MEMORY/BME, alocă și mapează buffere DMA, rulează firmware GPU în RAM, scrie SS0 și cere exact un FLR. Nu face flash BIOS/VBIOS și nu modifică instalarea Windows sau Windows Boot Manager. Secure Boot și validarea shim trebuie să rămână active.

Poate apărea blocaj preboot, ecran negru, refuzul driverului, eroare de firmware sau necesitatea opririi fizice complete. Verificările de curățare reduc riscul de a porni Windows cu DMA nesigur; testele simulate nu garantează absența erorilor pe hardware. Nu există un procent de risc justificat sau o garanție de câștig. După un STOP nu se continuă în Windows în același ciclu și nu se repetă tentativa.

Înrolarea hashului nou modifică persistent lista MOK până la eliminarea intrării exacte. Nu autorizează automat alte binare, chei sau drivere Windows. `Esc`/timeout la promptul U anulează înainte de activarea MEMORY, dar nu elimină o intrare MOK deja înrolată.

## După acord: o singură încercare

1. Agentul consemnează acordul explicit pentru **copierea acestui candidat, hashul său MOK și o încercare fizică**. Scriptul `scripts/Deploy-AuthorizedUnlock.ps1` verifică acordul și prerequisites, identifică exact SanDisk-ul, păstrează în backup CAPTURE/logurile/PROM-ul, copiază assets înaintea executabilului și recitește fișierele. Nu formatează, nu bootează și nu înrolează nimic automat.
2. După confirmarea copierii: salvează lucrul, conectează alimentatorul și păstrează același profil ASUS/monitoare ca la referință. Oprire completă prin Win+R → `shutdown /s /t 0`. La pornire folosește Esc pentru meniul temporar și alege UEFI SanDisk.
3. La refuzul inițial al imaginii noi: Enter pe OK, eliberează tasta, apoi Space o dată la numărătoarea MOK. Alege **Enroll hash from disk → M6501PROBE → EFI → BOOT → grubx64.efi**, identificând hashul MOK de mai sus. Păstrează Secure Boot activ. Nu selecta shim/mmx64, nu șterge MOK și nu reseta cheile firmware.
4. După înrolare/reboot, alege USB din nou. Numai dacă ai aprobat încercarea și aplicația cere **«Press U for this one attempt»**, apasă U o dată în 30 secunde. Esc/timeout anulează. Nu scoate stickul și nu întrerupe o tranzacție care progresează.
5. La succes, aplicația trebuie să pornească Windows Boot Manager existent în același boot. Lasă stickul conectat și anunță revenirea la desktop. **Nu reporni înainte de copierea logului și benchmarkul imediat.** Nu declara succes doar după apariția desktopului.
6. Dacă revine în boot menu, apare STOP, un ecran negru persistent sau Windows nu pornește: nu relansa unlock. Pentru STOP/blocaj fă oprire fizică completă, scoate USB și încearcă pornirea normală Windows. Dacă sistemul nu răspunde, ține apăsat Power până se oprește complet. Analizăm logul înaintea oricărei încercări noi. Oprirea completă este procedura de recuperare propusă; revenirea după un unlock real nu a fost încă testată pe acest laptop.

O nouă afișare MokManager după o înrolare corectă poate fi provocată și de un status returnat de aplicație. Nu se presupune automat că trebuie șterse/reînrolate cheile. Logul USB este sursa de diagnostic; nu este necesară fotografia textului care dispare repede.

## Criterii după prima încercare

Logul trebuie să demonstreze FWSEC scratch/WPR corecte, SS0 `0x88888888`, SS1 păstrat, un singur FLR, GFW complet/GSP oprit, BME oprit, zero mapări/alocări DMA rămase, atribute PCI restaurate și handoff Windows curat. La oricare verificare eșuată aplicația oprește continuarea; nu folosește un readback PIO drept dovadă de execuție firmware.

În Windows verificăm Secure Boot/MOK, driverul 580.97 și evenimentele, apoi rulăm GEMM identic cu referința și comparatorul. Nu schimbăm driverul, puterea sau frecvențele pentru a produce un câștig. Pentru SS0-only nu cerem accelerare TF32. Sunt necesare ulterior perechi A/B independente, boot normal de revenire și teste idle/sleep/resume; aplicația USB nu este serviciu Windows de reactivare după suspend. Acordul inițial descris aici este pentru **o singură încercare**, nu pentru repetări automate.

## Recompilare locală

Dependențele și versiunile rămân cele din `config/sources.lock.json`, cu compilatorul portabil și venv existente. Folosește o destinație nouă pentru a păstra dovezile și hashurile vechi:

```powershell
.\.venv\Scripts\python.exe tools/build.py --board config/board.reviewed.json --output build/candidate-REBUILD
.\.venv\Scripts\python.exe tools/test.py --build-root build/candidate-REBUILD
.\.venv\Scripts\python.exe tools/test_capture_transaction.py --evidence results/physical-capture-20261025-201848 --build-root build/candidate-REBUILD
.\.venv\Scripts\python.exe tools/stage_usb.py --mode candidate --image-root build/candidate-REBUILD --output build/release-REBUILD/USB-CANDIDATE
```

Aceste comenzi construiesc fișiere și rulează teste simulate. Un executabil cu hash diferit necesită revizie și autorizare nouă; nu se înlocuiește pe stick imaginea aprobată printr-o recompilare neidentificată.
