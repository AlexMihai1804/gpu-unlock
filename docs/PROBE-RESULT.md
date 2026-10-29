> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# PROBE fizic — 25 octombrie 2026

**Rezultat: trecut, în patru rulări.** Aplicația termină inventarul și revine imediat la firmware; afișarea pentru o fracțiune de secundă urmată de meniul de boot este compatibilă cu acest rezultat. Nu este nevoie de fotografie pentru a confirma PROBE, fiindcă logul este scris și închis pe USB înainte de ieșire.

Logurile au fost copiate fără modificare în `results/physical-probe-20261025-190741/RUN00/` până la `RUN03/`. Toate înregistrează:

```text
SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero
SMBIOS M6501RM_product=1 BIOS_313=1
PCI 0000:01:00.0 id=252010de subsystem=13131043 classrev=030000a1 command=0000 ROM_bytes=148992
TARGET exact_matches=1
GOP owner=16811002 independent_AMD=1 framebuffer=0x7e70000000 bytes=18662400
PROBE complete: no GPU config writes, no MMIO, no firmware load. display_safe=1
EXIT status=0 GPU_MMIO_writes=0
```

Hashul fișierului executat a fost reverificat pe USB și este `8f099671f487eca54c7584d913ba29b133f40cc6d86cb1c7e325344d2f509070`. Nu a fost recompilat sau înlocuit după înrolare.

Colectarea administrativă doar pentru citire a fost repetată după test, în `results/uefi-post-probe-20261025-190816/`. Aceasta confirmă SecureBoot=1 și SetupMode=0, iar MokListRT include exact hashul PE/Authenticode `7ea0fcecbecd80da16abca6258aee855b48c4c954602bb810d56b71e0cf498ea` al PROBE.

PK, KEK, db și dbx sunt identice octet cu octet cu exportul anterior. Blocul Windows Boot Manager din inventarul BCD este identic, cu aceeași cale și primul în ordine. Inventarul firmware în ansamblu **diferă**: intrările generice CD/DVD/removable/network anterioare sunt înlocuite în listare de intrarea concretă `UEFI: SanDisk, Partition 1`. Proiectul nu a emis comenzi de scriere BCD/BootOrder; nu atribuim totuși o lipsă de schimbări întregului inventar firmware. Datele brute înainte/după sunt păstrate.

Driverul raportat în Windows rămâne 580.97, VBIOS 94.06.38.00.38. GUID-ul partiției EFI Windows a fost reverificat: `11111111-1111-4111-8111-111111111111`, disc intern 0, partiția 1, identic cu profilul pregătit.

Analiza reproductibilă a dovezilor locale, fără scrieri hardware:

```powershell
.\.venv\Scripts\python.exe tools/review_probe.py --evidence results/physical-probe-20261025-190741 --post results/uefi-post-probe-20261025-190816
```

Raportul rezultat este `results/physical-probe-20261025-190741/probe-review.json`.

Ce rămâne de verificat

PROBE demonstrează lanțul shim/MOK/aplicație pe firmware-ul ASUS și inventarul citit. Nu demonstrează pornirea Windows prin funcția HANDOFF sau deblocarea GPU. PCI Command este zero în preboot, iar RomImage expusă de UEFI are 148.992 bytes; nu este captura PROM completă de 1 MiB necesară analizei FWSEC. Exclusivitatea PCI, activarea temporară MEMORY, restaurarea, descriptorii FWSEC și registrele de layout/fuse vor fi verificate numai în etapa CAPTURE autorizată separat.

După PROBE a fost testat HANDOFF, folosind Windows Boot Manager existent și GUID-ul reverificat, fără scrieri GPU. Utilizatorul l-a autorizat, noul hash a fost înscris în MOK și Windows a pornit prin această rută. [Rezultatul HANDOFF](HANDOFF-RESULT.md) include benchmarkul de control și avertismentul PCIe care necesită comparație cu un boot Windows direct fără USB. Captura și deblocarea rămân pentru etape distincte.
