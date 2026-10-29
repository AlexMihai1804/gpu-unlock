> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Pornire automată internă, fără USB — pregătită, neinstalată

Utilizatorul a cerut deblocare implicită și utilizare fără USB. Seria B3/A4 a fost înlocuită cu această cerere; B3 nu a fost executat. B1/B2 și controalele normale A2/A3 au trecut deja. Nu mai cerem repetarea aceleiași serii de benchmarkuri.

## Comportamentul pregătit

La pornire, firmware-ul încarcă shim Microsoft-signed, apoi aplicația locală acceptată prin hash MOK. Aplicația așteaptă **5 secunde**, timp în care **Esc** anulează deblocarea și pornește Windows normal. Altfel execută automat verificările și tranzacția SS0-only, apoi pornește Windows Boot Manager existent. Nu trebuie apăsat U și nu trebuie conectat USB.

Acesta este un mecanism de pornire. Nu reactivează GPU-ul din Windows după sleep, D3cold sau resetarea driverului; persistența în aceste situații rămâne nevalidată. Un câștig pierdut după asemenea evenimente nu trebuie prezentat ca deblocare permanentă.

## Modificările concrete propuse

| Element | Schimbarea propusă |
|---|---|
| Volumul E:, disc 1, partiția 3 | Reducere de la 100 GiB la **99,5 GiB**, folosind Resize-Partition; GUID-ul și începutul partiției rămân aceleași |
| Spațiul eliberat | Partiție nouă **512 MiB FAT32**, eticheta **M6501GPU**, tip GPT ESP, pe discul secundar |
| Fișierele noi | Numai în `\EFI\M6501GPU\` pe noua partiție: shim, MokManager, aplicația, cinci active GPU, licențe și loguri |
| Ordinea UEFI | O intrare nouă **M6501 GPU automatic** înaintea ordinii originale; intrările originale rămân byte-identice și sunt salvate pentru revenire |
| MOK | O singură înrolare fizică a hashului noului `grubx64.efi`; PK/KEK/db/dbx nu se modifică |
| Discul Windows, C: și ESP Windows | Nu se redimensionează și nu se copiază fișiere pe ele; Windows Boot Manager nu se înlocuiește |

Partiția EFI Windows are aproximativ **26,4 MiB liberi**. Pachetul necesită **86.482.896 bytes**, aproximativ 82,5 MiB, deci nu încape acolo. Discurile nu au suficient spațiu nealocat. Windows a raportat că E: poate fi redus cu 512 MiB. Ruta aleasă folosește o partiție FAT32 dedicată, fără a depinde de suportul NTFS al firmware-ului ASUS. Inspecția este în `results/internal-boot-inspection-20261025-221021/inspection.json`; montarea temporară de inspecție a ESP a fost eliminată.

## Riscul și recuperarea

**Redimensionarea E: este riscul nou asupra datelor.** Limita de shrink raportată de Windows nu garantează lipsa coruperii în cazul unei probleme de disc sau întreruperi. Datele importante de pe E: trebuie salvate înainte de aplicare; metadatele și copia ordinii de boot nu constituie un backup al datelor E:. Nu s-a făcut acel backup de date în cadrul pregătirii.

Deblocarea folosește firmware GPU în RAM, DMA și un FLR. Două porniri manuale reușite sunt dovezi utile, dar nu garantează stabilitatea versiunii automate sau lipsa blocajelor. Nu facem flash BIOS/VBIOS. O tranzacție eșuată cu stare nesigură produce STOP și cere oprire fizică completă; nu se continuă automat în Windows după asemenea eșec.

Înaintea scrierilor GPU, o anulare, verificare respinsă sau imposibilitate de a scrie logul duce la pornirea normală, numai după restaurarea accesului și eliberarea resurselor. Dacă loaderul Windows nu poate fi încărcat, aplicația returnează firmware-ului; această ramură nu promite un Windows funcțional indiferent de eroare.

Pentru recuperare după blocaj: oprire completă, apoi meniul ASUS Esc și alegerea **Windows Boot Manager** original. Pentru dezactivarea implicitului după revenire, scriptul de mai jos restaurează numai ordinea UEFI salvată și elimină numai noua intrare dacă este încă identică. Nu șterge partiții, nu extinde E: și nu șterge MOK sau cheile platformei.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Disable-InternalAutomatic.ps1 -InstallDirectory 'CALEA-DIN-results-latest-internal-install.txt'
```

## Executabilul concret și verificările terminate

- Build: `build/automatic-20261025-v2/M6501-AUTOMATIC.EFI`.
- SHA-256 fișier: `07a4e62f680122b9c2291729f41e3d92045f87dafb262ba7bad619eb3f6542e6`.
- Hash MOK PE/Authenticode: `433c71743989ae1ad24dff7bf9b47052270d3f85778f750226cb787531d5ae93`.
- Pachet pregătit: `build/internal-release-20261025-v1/`; nu este copiat pe disc sau USB.
- Nucleul tranzacției GPU are același SHA-256 de sursă ca v3 validat fizic. Sunt păstrate SS1 din bootul curent, verificările ROM/chip/fuse/GOP/PCI și oprirea la eșec nesigur.
- 217 verificări native pentru temporizare, anulare, erori de tastatură/timer/log, interdicția handoff-ului după activare/DMA și selectarea unei partiții ESP interne; 40 de teste Python trecute.
- Testele native pentru PCI, SHA-256, DMA/FLR și 20 de scenarii de tranzacție simulate au trecut. Separat au trecut 20 de scenarii pe ROM-ul/PCI-urile salvate de pe acest laptop și 13 cazuri de preflight, cu toate scrierile hardware interzise.
- OVMF/QEMU a executat **acest executabil**, de pe NVMe intern emulat, cu SecureBoot=1 și MOK virtual. Logul privat a fost creat, absența GPU-ului a fost respinsă și loaderul Microsoft real a fost pornit până la eroarea BCD absent, așteptată în VM. Nu a fost atașat un disc fizic, GPU sau rețea.
- Scripturile PowerShell au trecut parsarea, helperul C# limitat la BootOrder/Boot#### a fost compilat și codificarea opțiunii GPT a fost verificată. **Instalatorul, redimensionarea E: și scrierile NVRAM nu au fost executate.** Testele nu validează încă integrarea instalatorului cu serviciile Storage/NVRAM reale ale acestui Windows.

Rapoarte: `results/automatic-v2-host-tests.log`, `results/automatic-v2-saved-board-tests.log`, `results/automatic-v2-virtual-internal-boot.log`, `results/automatic-installer-offline-checks.json`. Încercările inițiale eșuate ale colectorului/harnessului sunt păstrate separat; au fost probleme de montare/declarații/dependențe locale, fără tranzacții GPU sau redimensionări.

## Compilare și aplicare

Instrucțiunile de compilare sunt în [AUTOMATIC-INTERNAL-BUILD.md](AUTOMATIC-INTERNAL-BUILD.md). Planul exact, hashurile instalatorului și pachetului sunt în `results/automatic-internal-ready.json`. Instalatorul verifică un acord care fixează hashul acestui plan și aprobă explicit reducerea E:, noua partiție, prioritatea de boot și înrolarea hashului MOK. Nu generează singur un acord și nu repornește automat laptopul.

După acord, instalatorul pregătește noua partiție, recitește fișierele, salvează variabilele originale și activează noua intrare. La prima pornire fizică va fi necesară înrolarea MOK: **Enroll hash from disk → M6501GPU → EFI → M6501GPU → grubx64.efi**, confirmând numai hashul de mai sus, apoi reboot. După înrolare pornirea devine automată. Verificăm o singură pornire a acestei versiuni și benchmarkul din același boot, fără reluarea seriei B3/A4.

Ordinea și opțiunile sunt cele definite de [specificația UEFI Boot Manager](https://uefi.org/specs/UEFI/2.11/03_Boot_Manager.html). Nu se înlocuiește loaderul Microsoft, nu se dezactivează Secure Boot și nu se resetează lista de chei. Acceptarea noii intrări de către ASUS și scrierea BootOrder prin Windows trebuie verificate la aplicarea autorizată; dacă firmware-ul sau Windows o refuză, nu se forțează prin ocolirea politicilor de securitate.
