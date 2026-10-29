> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Dovezi și decizie tehnică — 25 octombrie 2026

Actualizare după testele fizice: PROBE, HANDOFF și CAPTURE au trecut cu Secure Boot activ. Captura a confirmat GOP AMD, chip `0xb76000a1`, ROM complet, fuse și layout de 6 GB; colectarea UAC reluată confirmă trustul și cele trei hashuri MOK. [Rezultatul CAPTURE](CAPTURE-RESULT.md) și [candidatul local v3](UNLOCK-CANDIDATE-v3.md) delimitează starea curentă. Deblocarea fizică rămâne neexecutată. Analiza inițială de mai jos păstrează contextul și limitele cercetării, inclusiv afirmațiile despre ce era încă de verificat înainte de boot.

Date locale confirmate: M6501RM.313, GPU 2520 A1 / 1313:1043, 6 GB, VBIOS 94.06.38.00.38, NVIDIA 580.97. Windows este Pro Insider Preview build **29680**, diferit de sistemele din rapoartele externe. AMD iGPU este `1002:1681`; prezența sa în Windows nu dovedește proprietarul GOP în UEFI. După colectarea aprobată prin UAC, variabilele directe confirmă SecureBoot=1 și SetupMode=0; TPM este funcțional, BitLocker dezactivat.

Proiecte și ce demonstrează

- [Zagitta/gpu-unlock](https://github.com/Zagitta/gpu-unlock): nucleu Linux înainte de legarea driverului, FWSEC/V67, selectori și FLR. Nu este un driver Windows și nu poate fi instalat direct aici. README-ul descrie în principal cipuri desktop; detectarea trebuie verificată separat pentru 2520.
- [Raportul #53](https://github.com/Zagitta/gpu-unlock/issues/53): GA106M 2520 pe ASUS GA401QM, Linux, Secure Boot activ și modul semnat MOK; îmbunătățiri FP16/BF16 raportate. BIOS/VBIOS, alimentarea și driverul diferă. Demonstrează o posibilitate pe familia de cipuri, nu lanțul UEFI Windows.
- [Raportul #58](https://github.com/Zagitta/gpu-unlock/issues/58): ASUS FA506QM, subsystem 1043:16a2, VBIOS 94.06.17.00.5F, Windows cu driver 610.91; Secure Boot era **dezactivat**. Adaptarea a păstrat SS1 și a gestionat Command=0, ROM UEFI trunchiat și layout de 6 GB. Aceste particularități justifică verificările locale, nu copierea valorilor plăcii.
- [craftingmod/rtx30-unlock](https://github.com/craftingmod/rtx30-unlock/tree/5c076dc4ee7fa369639669fa591ac74d8f6dfcd8): bază nativă PE/COFF, EDK2, acces PCI verificat, firmware cu hashuri, controlul duratei de viață DMA și FLR. Varianta de aplicație upstream are presupuneri și trasee diferite; nu o folosim direct ca BOOTX64.
- [Experimentul GA106 desktop](https://github.com/predator0321/rtx3060-ga106-uefi-experiment/tree/ca3041b77eb933c594bfd637bb6c71107bef94d2): 2504 desktop, alt subsystem, alt driver/VBIOS și GNU-EFI. Confirmă utilitatea SS0-only și a selectării Windows prin GUID; performanța desktop nu este o predicție pentru laptop.
- [Articolul Wccftech](https://wccftech.com/nvidia-geforce-rtx-3090-ti-gets-nearly-80-fp16-bf16-compute-boost-with-linux-based-unlocking-trick/) este o introducere; deciziile de implementare se bazează pe surse și rapoarte primare.

Adaptarea locală reutilizează transportul și tranzacția fixate din craftingmod, fără experimentele sale de reconfigurare GOP. Patchul local elimină scrierea SS1 și schimbă atât verificarea pre-FLR, cât și cea post-FLR pentru a cere SS1 inițial. Păstrarea SS1 este verificată inclusiv prin interzicerea oricărei scrieri la registrul său în testul de tranzacție.

Secure Boot

[shim upstream](https://github.com/rhboot/shim/blob/main/README.md) descrie validarea celui de-al doilea executabil și serviciile de încărcare. Versiunea 16.1 oferă înlocuitori LoadImage/StartImage; folosim aceste servicii din tabela primită, fără încărcare manuală de imagini neverificate. SBAT și separarea secțiunilor executabile de cele inscriptibile sunt cerințe ale buildului local. Absența importurilor Windows nu dovedește compatibilitatea tuturor firmware-urilor.

Am extras local shim 16.1 din [pachetul Debian shim-signed](https://packages.debian.org/trixie/shim-signed) și MokManager din pachetul de helpers corespunzător, cu SHA-256 fixate în `config/sources.lock.json`. Verificarea Windows a identificat semnatarul Microsoft Windows UEFI Driver Publisher, issuer Microsoft Corporation UEFI CA 2011; furnizorul de trust Windows nu are o rădăcină de încredere pentru acest lanț. Aceasta nu este o verificare a db/dbx UEFI. Hashurile pachetelor au fost comparate cu metadatele Debian descărcate prin HTTPS; nu pretindem o verificare suplimentară OpenPGP a arhivei.

Exportul direct arată opt certificate în db și 447 de intrări SHA-256 în dbx. Imaginea shim are două semnături încorporate, cu certificate CA 2011 și CA 2023 identice cu cele din db. Hashul PE/Authenticode calculat local este `f4166948f7adafa71e45c7ca5d30d97f78f382ecf1e3c8e4767b1ec1770cd52f`; corespunde digestului din conținutul ambelor semnături și nu apare în dbx. Instrumentul `tools/audit_trust.py` face doar această preverificare structurală/hash/revocări disponibile, nu validare criptografică completă a PKCS7, timestampurilor sau politicii firmware. Acceptarea reală trebuie testată la boot. Variabilele shim RT întorc ERROR_ENVVAR_NOT_FOUND în bootul Windows curent; nu interpretăm aceasta ca dovadă că MokList persistent este gol.

Pentru primul test propun **MOK cu hash pentru un singur executabil**, înrolat fizic prin MokManager. [Documentația SUSE](https://documentation.suse.com/sled/15-SP7/html/SLED-all/cha-uefi.html) descrie opțiunile Enroll hash/key from disk; sursa MokManager permite același mecanism. Hashul înscris este hashul PE/Authenticode calculat de MokManager, **nu** simplul SHA-256 al fișierului din manifest.

O alternativă pentru iterații este un certificat local pentru bootloader, cheia păstrată offline și semnarea aplicației cu `sbsign`. Certificatul nu trebuie restricționat la semnarea modulelor kernel prin OID-ul `1.3.6.1.4.1.2312.16.1.2`; o MOK Ubuntu creată pentru DKMS poate avea această restricție. Nu am generat sau înrolat o astfel de cheie. MOK pentru bootloader nu semnează automat drivere kernel Windows și nu trebuie folosit pentru a slăbi Code Integrity Windows.

Alte variante: un hash/certificat adăugat în db de firmware ar permite pornirea directă, dacă ASUS permite append fără ștergerea cheilor existente. Aceasta schimbă trustul platformei și nu este preferată. Certificatele publice Canonical și ASUS deja prezente nu oferă cheile private necesare semnării aplicației. Fără o autoritate deja disponibilă sau o înrolare nouă nu putem autoriza legitim executabilul local doar copiindu-l pe USB.

MOK este stocat în variabile UEFI persistente, separat de PK/KEK/db. În plus, pornirea shim poate scrie propriile variabile de stare/SBAT și extinde PCR-uri TPM. De aceea nici măcar pornirea USB cu PROBE nu este prezentată ca o operație fără niciun efect asupra NVRAM; nu a fost efectuată. Deblocarea GPU și înrolarea trustului sunt aprobări distincte.

Particularități încă neconfirmate pe ASUS

[ASUS documentează](https://www.asus.com/support/faq/1013017/) meniul temporar de boot cu Esc și USB FAT32. Recomandările generale de dezactivare Secure Boot din acea pagină nu sunt aplicate acestui proiect. [Pagina ASUS pentru laptopuri](https://www.asus.com/ca-en/support/faq/1050047/) subliniază diferențele de interfață BIOS; nu confirmă ce operații Key Management oferă M6501RM.313. Nu am găsit o specificație primară care să garanteze append la db pe acest firmware.

Nu este necesar Key Management pentru ruta shim/MOK dacă firmware-ul acceptă shim semnat, nerevocat. Trebuie însă exportate db/dbx și verificate politicile effective înainte de boot. Nu se șterg chei, nu se trece în Setup Mode, nu se folosește Other OS pentru a obține SecureBoot=0 și nu se resetează TPM.

Pentru 6 GB se calculează layout-ul din registrele reale, cu limitele și verificările nucleului fixat; adresele 6 GB ale altui raport nu sunt introduse ca profil. FWSEC se extrage din PROM-ul **acestei plăci**; o RomImage UEFI de aproximativ 65 KB poate fi incompletă. Captura locală citește 1 MiB din BAR0 și salvează hash, descriptor, registre de layout și fuse. Nu folosește un ROM descărcat de la alt model.

Optimus, ACPI D3cold, sleep/resume sau reinițializarea driverului pot pierde selectorii după preboot. Nucleul Linux are logică de resume; aplicația USB nu oferă un serviciu Windows de reactivare. Trebuie măsurat imediat, după idle și după suspend; nu promitem persistență. Limita termică/TGP poate micșora câștigul, iar workloadurile limitate de memorie pot rămâne neschimbate.

Pragul pentru a declara funcționarea este: lanț Secure Boot valid pe laptop, log tranzacție complet/curat, driver fără erori, rezultat numeric corect și avantaj repetat în benchmarkuri controlate. Acest prag nu este încă îndeplinit.

Verificări suplimentare fără modificarea Windows

Citirea ACPI/SMBIOS prin [GetSystemFirmwareTable](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemfirmwaretable) a confirmat șirurile `M6501RM.313` și `Vivobook_ASUSLaptop M6501RM_M6501RM`, exact cele cerute în adaptor. Au fost citite tabelele disponibile și DSDT direct, fără execuția metodelor AML sau acces la memoria fizică. VFCT include PCIR `1002:1681`, deci ROM AMD integrat; nu este PROM NVIDIA. Există 25 SSDT enumerate, dar Windows returnează numai primul pentru această semnătură repetată. Nu deducem că celelalte nu conțin metode GPU. Tabela de licențiere MSDM este exclusă de colector. Raportul este în `results/firmware-tables-20261025-v2/report.json`; fișierele brute locale SMBIOS pot conține identificatori și sunt excluse din arhiva sursă.

Lanțul shim 16.1 → aplicație autorizată prin MOK → LoadImage/StartImage a fost exercitat în QEMU/OVMF cu copii ale bazelor publice exportate, exclusiv în fișiere virtuale. Au trecut șase verificări, inclusiv refuzul hashului modificat/revocat și pornirea copiei Windows Boot Manager. [Raportul VM](VM-LAB.md) delimitează exact ce s-a verificat. Firmware-ul ASUS, TPM, GPU-ul și instalarea Windows nu au fost atașate VM; rezultatele nu înlocuiesc validarea fizică.
