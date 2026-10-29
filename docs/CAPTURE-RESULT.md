> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# CAPTURE fizic: reușit, fără deblocare

Logul `RUN05/UNLOCK.TXT` și ROM-ul `PROM00.ROM` au fost copiate de pe stickul identificat prin serial și GUID. Toate copiile au fost verificate SHA-256. Dovezile sunt în `results/physical-capture-20261025-201848/`; verificarea reproductibilă este în `capture-review.json`.

Captura s-a executat cu SecureBoot=1, SetupMode=0 și validarea shim activă. Identitatea ASUS/BIOS/PCI, GOP-ul AMD, fereastra punții și exclusivitatea PCI au trecut. MEMORY a fost activat temporar (`Command=2`), apoi restaurat cu `MEM_RESTORE status=0 confirmed=1 command=0`. Ieșirea este `EXIT status=0 GPU_MMIO_writes=0`. Activarea MEMORY a fost o scriere temporară PCI, chiar dacă nu au existat scrieri MMIO GPU. Nu s-au executat firmware GPU, DMA, FLR, unlock sau flash.

| Dată observată | Valoare |
|---|---|
| Chip | `0xb76000a1` |
| VRAM | 6144 MiB |
| SS0 / SS1 în starea capturată | `0x10420030` / `0x3` |
| PROM | 1.048.576 bytes |
| SHA-256 PROM | `dce995afb0e825c9640488b55054179ebc15c77d38c00ed45a05f7e2701433e7` |
| FWSEC | engine `0x400`, ucode 9, 3 semnături, versiuni `0x7` |
| FWSEC fuse / versiune selectată | `0x3` / 2 |
| Booter fuse / versiune selectată | `0x1` / 1 |

Parserul fixat a acceptat ROM-ul salvat. Separat, verificarea offline cu funcțiile native originale a acceptat selecția semnăturilor FWSEC/Booter, mapperul FRTS V3 și calculul zonelor de memorie pentru datele reale de 6 GB. Modificările de probă au existat numai în buffere CPU. Calculul nu aplică lock-ul MMU ca rezervare la vârful VRAM, deoarece limita sa superioară citită nu coincide cu vârful celor 6 GB; acesta este comportamentul codului fixat, nu o valoare împrumutată de la alt laptop. Vezi `offline-preflight.json` și `tools/preflight_capture.py`.

Benchmarkul de control a folosit aceeași configurație ca referința: FP16 **27,162 TFLOPS**, BF16 **27,623 TFLOPS**, TF32 **13,845 TFLOPS**, FP32 **9,327 TFLOPS**. Abaterea maximă este **0,256%**, iar toate cele patru ieșiri complete sunt identice la nivel de biți. Fișier: `results/capture-control-2026-10-25.json`. Aceasta verifică funcționarea după captură, fără să valideze deblocarea sau stabilitatea de durată.

Colectarea administrativă reluată după acordul utilizatorului a trecut: `results/uefi-post-capture-20261025-203931/` confirmă SecureBoot=1/SetupMode=0, validare shim activă, hashul exact CAPTURE în MokListRT, PK/KEK/db/dbx identice cu exportul inițial și Windows Boot Manager identic/primul. Anulările UAC anterioare rămân în rapoartele de lansare, dar verificarea nu mai este în așteptare. După benchmark nu există evenimente Display/nvlddmkm în această pornire. Verificarea a găsit avertismentul corectat al portului Realtek deja reprodus și fără USB; cauza rămâne neconfirmată.

Verificarea trustului, revizia statică și construirea candidatului local v3 sunt încheiate. Testele pe datele capturate au trecut cu hardware simulat; [candidatul v3](UNLOCK-CANDIDATE-v3.md) rămâne neaplicat și necesită acord separat. Profilul pending/vechiul executabil rămân blocate, iar stickul conține CAPTURE. Nu mai este necesară repetarea capturii pentru datele deja obținute.

Un candidat activat trebuie prezentat cu hashuri, teste și riscuri înainte de acordul distinct pentru copiere, MOK și execuție. După un prim test autorizat se verifică logul tranzacției, pornirea Windows, Secure Boot, corectitudinea și performanța FP16/BF16; apoi sunt necesare perechi de boot A/B și revenire la boot normal. Acceptarea offline nu demonstrează că firmware-ul GPU sau driverul 580.97 vor accepta tranzacția.

Comenzi de analiză, fără pornire UEFI sau acces la dispozitiv:

```powershell
.\.venv\Scripts\python.exe tools/inspect_rom.py results/physical-capture-20261025-201848/RTX-UNLOCK/PROM00.ROM
.\.venv\Scripts\python.exe tools/review_capture.py --evidence results/physical-capture-20261025-201848 --control results/capture-control-2026-10-25.json --post results/uefi-post-capture-20261025-203931
```

`preflight_capture.py` păstrează raportul existent; pentru o nouă analiză se folosește o copie nouă a dosarului de dovezi. ROM-ul și exporturile identificabile rămân locale și se exclud din arhivele publice de cod.
