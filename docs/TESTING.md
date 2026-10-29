> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Testare etapizată și recuperare

**Starea curentă: A3 a trecut**, cu abatere maximă 1,05% și ieșiri identice, Secure Boot activ, cheile platformei/Windows Boot Manager neschimbate și zero erori Display/nvlddmkm. Windows este în boot normal. Urmează [B3 deja autorizat](START-B3-v3-AUTHORIZED.md), apoi A4. [Raport A3](NORMAL-RETURN-A3-RESULT-v3.md). Paragrafele următoare păstrează istoricul etapelor.

Actualizare v3: **B1, controlul normal A2 și al doilea unlock B2 au trecut**, cu Secure Boot activ, restaurare PCI/DMA și Windows/driver 580.97. În B1: FP16 +57,00%, BF16 +61,50%. În A2: abatere maximă 0,76% față de referință. În B2: FP16 +57,89%, BF16 +58,76%, toate ieșirile identice. Vezi [B1](UNLOCK-RESULT-v3.md), [A2](NORMAL-RETURN-RESULT-v3.md) și [B2 cu pașii A3](UNLOCK-B2-RESULT-v3.md). [Planul B2/B3](REPRODUCIBILITY-v3-PLAN.md) a fost autorizat prin „aprob”; B2 a consumat prima dintre cele două încercări suplimentare. Urmează controlul normal A3; B3 se execută numai după A3 reușit, în acordul deja dat. Procedurile prospective și notele despre aprobări de mai jos descriu istoricul etapelor inițiale, nu starea curentă.

Starea curentă: benchmark de referință executat; colectare administrativă executată prin UAC; PROBE copiat pe stickul SanDisk Ultra F: după formatarea FAT32 autorizată explicit. Toate cele 13 fișiere copiate au fost recitite și verificate. Inventarul partițiilor interne a rămas identic după pregătire. Pornirea PROBE și înrolarea hashului său au fost ulterior autorizate și au trecut fizic. Deblocarea nu a fost executată. Pașii următori și orice nouă modificare de trust se fac numai după acordul pentru etapa respectivă.

Actualizare după testele fizice: **PROBE și înrolarea hashului său au fost autorizate și executate**. Patru rulări au trecut. Vezi [PROBE-RESULT.md](PROBE-RESULT.md). **HANDOFF a fost autorizat, înrolat și executat; Windows a pornit și benchmarkul de control a trecut.** Secure Boot rămâne activ, ambele hashuri sunt în MokListRT, iar PK/KEK/db/dbx și intrarea Windows Boot Manager sunt identice cu exportul anterior. Vezi [HANDOFF-RESULT.md](HANDOFF-RESULT.md). Controlul Windows direct fără USB a reprodus avertismentul PCIe corectat al portului Realtek; cauza rămâne neconfirmată. **CAPTURE a fost autorizat, executat cu succes, iar MEMORY a fost restaurat.** ROM-ul complet, analiza offline si benchmarkul de control sunt in [CAPTURE-RESULT.md](CAPTURE-RESULT.md). Exportul administrativ MOK/trust de dupa captura ramane in asteptare deoarece Windows a raportat anularea UAC. UNLOCK rămâne neautorizat și neexecutat.

Pachetele curente sunt în `build/release-20261025-v2/USB-*`; folderele vechi `build/USB-*` sunt depășite. Cele șase teste QEMU/OVMF din [VM-LAB.md](VM-LAB.md) au trecut, inclusiv respingerile de securitate și execuția loaderului Microsoft până la BCD lipsă în VM. Modificările din acele teste există numai în fișierele virtuale. Separat, PROBE și HANDOFF au fost validate fizic conform actualizării de mai sus; procedurile lor rămân mai jos ca referință.

Date necesare acum, fără aplicare

Pasul 1 a fost deja efectuat: exportul complet se află în `results/uefi-readonly-20261025-161851/`, iar analiza preliminară în `results/trust-audit-20261025/`. Instrucțiunile de mai jos rămân pentru repetarea colectării dacă starea sistemului se schimbă.

1. Deschide manual PowerShell ca Administrator și rulează scriptul de colectare. Privilegiile sunt necesare deoarece Windows a refuzat citirea directă a variabilelor UEFI în sesiunea curentă.

   ```powershell
   Set-Location 'C:\Projects\gpu-unlock'
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Collect-ReadOnly.ps1
   ```

   Politica din comandă este numai pentru procesul respectiv. Scriptul nu utilizează Set-SecureBootUEFI, nu modifică BCD și nu cere reboot. Rezultatul este un folder nou în `results/uefi-readonly-*`, cu `report.json`, `SecureBoot.bin`, `SetupMode.bin`, `PK.bin`, `KEK.bin`, `db.bin`, `dbx.bin`, variabilele shim accesibile și inventarul de boot. Fișierele de trust conțin certificate/hashuri publice, nu chei private. Logurile locale pot conține identificatori ai sistemului; nu trebuie publicate integral.

2. La o vizită ulterioară în BIOS, notează doar opțiunile vizibile la Security → Secure Boot / Key Management și dacă există boot temporar pentru USB UEFI. Nu schimba setări și nu salva modificări. În particular nu selecta Delete/Clear keys, Restore factory keys, Setup Mode, Other OS sau reset TPM. Ruta MOK nu presupune că BIOS-ul permite append în db.

3. ROM-ul original: dacă ai deja o funcție de salvare VBIOS disponibilă, se poate furniza fișierul nemodificat, versiunea și SHA-256. Un export scurt nu se completează artificial cu zerouri și nu se înlocuiește cu ROM-ul altui laptop. Alternativa pregătită este `M6501-CAPTURE.EFI`, care citește 1.048.576 bytes din PROM în etapa separată de mai jos. **Captura activează temporar accesul PCI MEMORY dacă inițial este oprit; necesită aprobarea acelei etape.**

Analiza unui fișier deja extras este doar locală:

```powershell
.\.venv\Scripts\python.exe tools/inspect_rom.py .\roms\original.rom
Get-FileHash -Algorithm SHA256 -LiteralPath .\roms\original.rom
```

Parserul folosit este chiar parserul FWSEC al nucleului fixat. Acceptarea unui fișier dovedește structura recunoscută, nu proveniența plăcii sau funcționarea fizică.

Etapa de trust și inventar — numai după aprobare

Se verifică mai întâi db/dbx exportate, versiunea și semnătura shim și eventualele variabile SBAT/MOK existente. Shim este 16.1 din pachetele Debian fixate, iar issuerul identificat local este Microsoft Corporation UEFI CA 2011. Prezența CA în db nu este suficientă dacă imaginea/certificatul este revocat. `Get-AuthenticodeSignature` din Windows nu este un simulator al politicii UEFI; rezultatul local este în `results/shim-windows-signature.json`.

Nu se folosesc shim vechi pentru a evita revocări și nu se dezactivează validarea MOK. Dacă firmware-ul refuză shim, testul se oprește și se analizează eroarea. Nu se modifică db/dbx/PK pentru a continua automat.

După aprobarea exactă a fișierelor și a înrolării:

1. Se copiază conținutul `build/release-20261025-v2/USB-PROBE` pe un USB FAT32 separat, identificat înainte de copiere. Nu se suprascrie partiția EFI Windows. Pachetul are `EFI/BOOT/BOOTX64.EFI` (shim), `mmx64.efi` și `grubx64.efi` (aplicația PROBE), plus `RTX-UNLOCK/` pentru loguri.
2. Se folosește meniul temporar ASUS, în mod obișnuit Esc la pornire, fără schimbarea BootOrder. Nu se urmează pașii generali ASUS de dezactivare Secure Boot pentru USB.
3. La prima execuție, aplicația locală neînrolată trebuie respinsă. MokManager poate oferi **Enroll hash from disk**. Această selecție modifică MokList și se confirmă numai cu aprobarea deja acordată pentru hashul executabilului exact. Se selectează aplicația `EFI/BOOT/grubx64.efi`, nu shim. Lipsa opțiunii sau un comportament diferit oprește procedura pentru analiză.
4. MOK utilizează hashul PE/Authenticode, calculat din fișier. Acesta diferă de SHA-256 al fișierului întreg din manifest. Manifestul verifică fișierele copiate; nu se introduce manual hashul său drept hash MOK.
5. După restart, PROBE scrie `RTX-UNLOCK/RUNxx/UNLOCK.TXT`. Se verifică modelul/BIOS-ul, BDF/subsystem, Command, ROM_bytes și că GOP este AMD. Aplicația PROBE nu accesează MMIO și nu încarcă firmware GPU.

**Chiar această etapă poate modifica variabilele proprii shim/SBAT și măsurători TPM, în plus față de înrolarea MOK aprobată.** Eticheta „fără scrieri GPU” descrie aplicația, nu lipsa tuturor efectelor loaderului asupra NVRAM.

Etapa de pornire Windows — fără unlock

După validarea PROBE se autorizează imaginea HANDOFF. Este un executabil diferit, deci are alt hash MOK. Se verifică separat `build/release-20261025-v2/USB-HANDOFF`.

Aplicația folosește calea existentă `\EFI\Microsoft\Boot\bootmgfw.efi` de pe partiția cu GUID-ul sistemului, cere o potrivire unică și folosește LoadImage/StartImage din tabela primită de la shim. Nu copiază sau modifică bootmgfw.efi și nu folosește `bcdedit /set`.

Criteriu de trecere: log HANDOFF-ONLY reușit, Windows pornește, `Confirm-SecureBootUEFI` rămâne True, SetupMode rămâne 0, validarea shim nu este dezactivată, driverul 580.97 și benchmarkul de control funcționează. Dacă Windows nu pornește prin această rută, nu se trece la deblocare.

Etapa de captură — fără FWSEC/V67/DMA/FLR

După acord pentru captura temporară și autorizarea hashului CAPTURE, se bootează `build/release-20261025-v2/USB-CAPTURE` dintr-o oprire completă, cu alimentare AC și fără dispozitive externe care ar putea muta GOP pe NVIDIA. Tasta **P**, în 30 de secunde, permite o singură captură. Esc/timeout anulează.

Înainte de activarea MEMORY se cer D0, capacități PCI valide, BME/MSI/MSI-X oprite, BAR0 alocat și punți cu ferestre MEM suficiente. Aplicația nu mută BAR-uri și nu programează punți. Dacă un driver UEFI deține placa sau GOP nu este independent, se oprește. MEMORY se gestionează prin `PciIo->Attributes()`, pentru a păstra sincronizat și cache-ul protocolului.

Fișiere de păstrat de pe USB:

- `RTX-UNLOCK/PROMxx.ROM`, exact 1 MiB, și hashul `PROM_SHA256` din log;
- `RTX-UNLOCK/RUNxx/UNLOCK.TXT`, inclusiv COLD, LAYOUT_REG, BOOTER_FUSE, FWSEC/FWSEC_FUSE și MEM_RESTORE confirmed=1;
- manifestul exact al executabilului pornit și exporturile Secure Boot de după etapă.

Captura nu încarcă firmware GPU, nu pornește DMA și nu dă FLR. Nu înseamnă „niciun acces hardware modificator”: MEMORY poate fi activat temporar. Orice eșec la restaurare cere oprire fizică completă și analiză; nu se repetă în același ciclu de alimentare.

Pregătirea variantei pentru placă

Se compară VBIOS-ul raportat, hashul ROM original, descriptorul FWSEC și versiunea fuse cu semnăturile disponibile. Se analizează layout-ul real de 6 GB, BAR-urile, punțile și proprietatea GOP. SS0 nu este fixat la o valoare istorică; SS1 este citit în fiecare încercare și păstrat. Driverul 580.97 și Windows build 29680 nu au fost validate de rapoartele externe.

Abia după această analiză se creează un profil separat `config/board.reviewed.json` cu chip/hash reale, GUID-ul Windows reverificat și evidence_reviewed=true. Se compilează, se repetă verificările și se prezintă noile hashuri pentru acord. Schimbarea profilului nu aplică nimic; schimbă doar fișierul ce ar putea fi autorizat ulterior.

Etapa de unlock — aprobare distinctă

Se pornește imaginea specifică plăcii după oprire completă, numai după acord. Tasta **U** confirmă o singură tranzacție în acel boot. Nu se activează testul doar prin înrolarea MOK. Copia veche cu evidence_reviewed=false refuză înainte de accesul PCI modificator; candidatul v3 separat a trecut prima încercare autorizată în RUN06. Pentru alte încercări se cere acord nou.

Pentru succes sunt obligatorii toate: hash PROM corect, FWSEC/WPR validate, SS0=88888888, SS1 nemodificat, exact un FLR, GFW complet și GSP oprit după FLR, BME=0, nicio mapare sau alocare DMA rămasă, atributele PCI originale restaurate și handoff Windows în același boot. Un rezultat de registru singur nu demonstrează accelerarea.

Orice eșec de tranzacție/curățare oprește handoff-ul și cere oprire completă. Nu există recuperare prin continuare automată în Windows atunci când starea DMA nu este demonstrată sigură.

Benchmark A/B

Se mențin driverul, cuBLAS, alimentatorul, profilul ASUS, temperatura inițială, aplicațiile deschise și monitoarele externe identice. Nu se schimbă limite de putere sau ceasuri. Se păstrează telemetria și evenimentele de driver/TDR/WHEA.

```powershell
# Referință nouă, după boot normal; benchmarkul nu face unlock.
.\.venv\Scripts\python.exe bench/gemm.py --label baseline-A2 --output results/baseline-A2.json

# Numai după un boot experimental autorizat și verificat:
.\.venv\Scripts\python.exe bench/gemm.py --label candidate-B1 --output results/candidate-B1.json
.\.venv\Scripts\python.exe bench/compare.py results/baseline-A2.json results/candidate-B1.json
```

Aceeași comandă fără parametri suplimentari folosește 8192³, 5×10, 4 s încălzire și GPU CUDA 0. Comparatorul refuză medii, GPU-uri, intrări sau parametri diferiți și rezultate care nu au trecut verificarea numerică. Ieșirea FP32 este folosită în ambele brațe. TFLOPS = 2N³ / timp, fără factor de sparsitate.

Se fac cel puțin trei perechi independente de boot normal/experimental și o revenire finală la boot normal. Se caută un avantaj FP16/BF16 repetat, mai mare decât variația probelor, cu control FP32 aproximativ stabil și temperatură/putere comparabile. Pentru SS0-only nu se cere accelerare TF32. Nu se cere sau promite dublarea performanței.

Se verifică hashurile întregii ieșiri și eroarea numerică; verificarea eșantionului nu demonstrează corectitudinea tuturor workloadurilor. Pentru utilizare reală se testează și aplicația țintă, cu aceleași date și setări. Nu se declară stabilitate de durată pe baza unui GEMM scurt.

După succesul inițial se măsoară separat după idle/D3cold și sleep/resume, apoi după boot normal direct. Aplicația USB nu reexecută unlock la resume. Un câștig pierdut după suspend trebuie raportat ca limitare, nu ascuns prin schimbarea profilului energetic.

Recuperare

Se oprește complet laptopul, se scoate USB-ul și se alege Windows Boot Manager existent. Ordinea de boot și ESP Windows nu au fost modificate de aplicație. După un eșec de firmware/DMA nu se încearcă relansarea aplicației în același ciclu de alimentare.

Eliminarea unei intrări MOK se planifică pe baza listei exacte înrolate și a utilitarului disponibil; nu se resetează întreaga MokList, deoarece poate conține chei ale altor sisteme. Nu se șterg PK/KEK/db pentru a elimina această aplicație. Scoaterea USB-ului oprește folosirea aplicației, dar nu șterge intrarea MOK persistentă. După oprire/boot normal se verifică prin benchmark revenirea la referință.
