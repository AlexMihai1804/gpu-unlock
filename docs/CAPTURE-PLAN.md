> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# CAPTURE autorizat — fără unlock

PROBE și HANDOFF au trecut fizic, iar benchmarkul de control are ieșiri identice cu referința. Controlul Windows pornit direct fără USB a reprodus avertismentul PCIe corectat al plăcii Ethernet Realtek. Prin urmare, avertismentul nu este specific pornirii prin HANDOFF; cauza și istoricul său anterior rămân neconfirmate. Secure Boot este activ și în control. Vezi `results/normal-boot-control-20261025-194422/comparison.json`.

**CAPTURE a fost autorizat, copiat și executat cu succes.** ROM-ul complet de 1 MiB, chipul și starea rece au fost obținute, restaurarea PCI și trustul de după etapă sunt confirmate, iar benchmarkul de control are ieșiri identice cu referința. Vezi [CAPTURE-RESULT.md](CAPTURE-RESULT.md). Ulterior s-a pregătit un [candidat local v3](UNLOCK-CANDIDATE-v3.md) cu profil revizuit și teste simulate trecute; nu este aplicat sau autorizat fizic. Profilul pending/vechiul candidat rămân blocate. Pașii de mai jos documentează etapa CAPTURE deja executată, care nu trebuie repetată acum.

Scopul acordului primit

1. Actualizarea aplicației `EFI/BOOT/grubx64.efi` de pe SanDisk cu CAPTURE, fără reformatare. Logurile PROBE/HANDOFF și executabilul HANDOFF sunt păstrate în copie locală înainte de actualizare. Shim/MokManager rămân identice, iar eticheta stickului rămâne M6501PROBE.
2. Pornirea CAPTURE prin același shim și înrolarea **hashului exact CAPTURE** în MOK, separat de cele două hashuri deja aprobate. Înrolarea este persistentă până la ștergerea intrării exacte; nu implică ștergerea sau înlocuirea PK/KEK/db/dbx. Shim poate actualiza propriile variabile de stare/SBAT, ca în etapele anterioare.
3. După verificările preboot și tasta **P**, o singură captură a ROM-ului/registrelor NVIDIA. Aplicația poate activa temporar bitul PCI **MEMORY** dacă este oprit, pentru a permite citirea BAR0. Apoi cere restaurarea și verificarea atributelor/Command originale.

Acest acord nu autorizează deblocarea GPU, încărcarea de firmware GPU, DMA, FLR, flash BIOS/VBIOS sau modificări Windows/BCD. CAPTURE este o aplicație separată, cu acestea excluse din harta sa de linkare. Activarea MEMORY este totuși o modificare temporară de configurație PCI; captura nu este prezentată ca o operație fără niciun efect hardware.

Fișiere și hashuri aprobate

- Pachet local: `build/release-20261025-v2/USB-CAPTURE/`.
- Executabil: `build/M6501-CAPTURE.EFI`, același cu `EFI/BOOT/grubx64.efi` din pachet.
- SHA-256 al fișierului: `2fc636dbc15b351a9e3139e4811a01e953b0d8bf99176e606774bdc248486022`.
- Hash PE/Authenticode SHA-256 pentru **MOK**: `7d073c9d54198ff2c18e9d27ad5531ce91bd0232a4c720f08351959356753f4a`.

PE AMD64 EFI_APPLICATION, NX, dynamic base, SBAT, relocări, secțiuni separate și fără importuri DLL; analizate din nou fără recompilare. Guardul PCI fixat a acceptat offline snapshotul real de 256 bytes. Exclusivitatea protocolului PCI, descriptorul BAR0 de 16 MiB, ferestrele punților, activarea/restaurarea MEMORY și lectura PROM au trecut ulterior pe hardware în RUN05.

Procedura pregătită, după acord

Se face oprire completă, se lasă alimentatorul conectat și se pornește USB-ul prin Esc, cu Secure Boot activ. Se înrolează noul hash din `M6501PROBE → EFI → BOOT → grubx64.efi`, apoi se repornește pe același USB. La mesajul «Press P for this one attempt» se apasă o singură dată **P**, în 30 de secunde. Esc/timeout anulează.

După captură se revine la firmware; CAPTURE nu pornește singur Windows. Nu se repetă încercarea pentru a fotografia textul rapid. Se revine în Windows normal și se citesc fișierele de pe USB:

- `RTX-UNLOCK/PROMxx.ROM`, exact **1.048.576 bytes**;
- `RTX-UNLOCK/RUNxx/UNLOCK.TXT`, cu PROM_SHA256, COLD, LAYOUT_REG, BOOTER_FUSE, FWSEC/FWSEC_FUSE, MEM_ENABLE și **MEM_RESTORE confirmed=1**;
- manifestul exact al aplicației executate.

O respingere sau un eșec de citire poate lăsa un log fără ROM; acesta se analizează înainte de orice repetare. Dacă restaurarea PCI nu este confirmată, aplicația se oprește cu mesaj STOP; se face oprire fizică completă și analiză, fără relansare în același ciclu. Există posibilitatea unui blocaj preboot, deci nu se garantează risc zero.

Analiza ROM-ului și a stării FWSEC se face ulterior, fără flash sau unlock. Un dump UEFI de 148.992 bytes nu va fi completat artificial cu zerouri. Orice build de unlock activat și orice test de performanță după unlock ar necesita o etapă nouă, cu dovezile revizuite și acord distinct.
