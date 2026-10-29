> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Verificări izolate — 25 octombrie 2026

Scopul este verificarea lanțului shim/MOK și a funcțiilor Secure()/LoadWindows() reale, fără pornirea USB pe laptop. QEMU 11.1.0 rulează prin TCG, cu OVMF Secure Boot și SMM. Modelul și BIOS-ul sunt **emulate** pentru test; nu reprezintă firmware-ul ASUS real. Nu există GPU NVIDIA emulat și nu se testează deblocarea GPU.

| Verificare | Rezultat observat |
|---|---|
| MOK cu hash autorizat | shim semnat pornește harnessul și PROBE; SecureBoot=1, SetupMode=0; PROBE refuză lipsa GPU-ului cerut |
| PROBE modificat cu un octet | LoadImage întoarce EFI_SECURITY_VIOLATION; copilul nu pornește |
| Hash PROBE adăugat în dbx virtual | EFI_SECURITY_VIOLATION, inclusiv când hashul este în MOK virtual |
| Secure Boot oprit numai în VM | Secure() și PROBE refuză continuarea cu EFI_SECURITY_VIOLATION |
| MOK absent în VM | shim afișează Verification failed: (0x1A) Security Violation; harnessul nu pornește |
| Handoff | funcția reală LoadWindows găsește GUID-ul GPT emulat, încarcă copia Microsoft bootmgfw.efi și o pornește; apare Windows Boot Manager, eroare 0xc000000f pentru BCD absent |

Eroarea BCD este rezultatul așteptat al testului izolat: imaginea virtuală conține numai loaderul, fără BCD sau instalare Windows. Confirmă executarea loaderului; nu confirmă un boot Windows complet pe ASUS. Harnessul a fost autorizat printr-un hash în varstore-ul virtual; PROBE prin alt hash virtual. Nu a fost parcursă interfața de înrolare MokManager pe firmware-ul fizic.

Izolare

QEMU primește doar un USB GPT/FAT32 de 128 MiB creat sub `build/vm-lab/` și o copie locală VARS.fd. Imaginea OVMF CODE este numai pentru citire. Comanda exclude configurațiile implicite și dispozitivele implicite (`-no-user-config -nodefaults`), folosește `-accel tcg`, `-nic none`, `-display none` și nu atașează discuri fizice, ESP, NVMe, TPM, GPU sau alte dispozitive ale gazdei. Nu folosește WHPX, Hyper-V sau WSL. Fiecare test are timeout de cel mult 50 s și închide procesul QEMU propriu.

PK/KEK/db/dbx exportate sunt certificate/hashuri publice, copiate în **fișierul** UEFI virtual cu virt-firmware. MOK și revocările de test sunt scrise numai în același fișier virtual. Nu există apeluri de scriere a variabilelor UEFI Windows în acest laborator. Loaderul Microsoft este doar citit din `C:\Windows\Boot\EFI\bootmgfw.efi` și copiat în USB.img local. Fișierul sursă și configurația Windows nu sunt modificate.

Reproducere

Se execută mai întâi compilarea normală din README și colectarea administrativă **numai pentru citire**, deja autorizată și efectuată în această sesiune. Colecția folosită aici este `results/uefi-readonly-20261025-161851`. Sunt necesare PK.bin, KEK.bin, db.bin și dbx.bin originale.

```powershell
python -m venv .venv-vm
.\.venv-vm\Scripts\python.exe -m pip install -r tools/requirements-vm.txt
.\.venv-vm\Scripts\python.exe -m pip install --no-deps virt-firmware==26.10
.\.venv\Scripts\python.exe tools/prepare_vm.py

foreach ($case in @('probe','tamper','dbx','secure-off','no-mok','windows')) {
    .\.venv-vm\Scripts\python.exe tools/vm_lab.py --case $case --timeout 25 --collection results/uefi-readonly-20261025-161851
    if ($LASTEXITCODE -ne 0) { throw "Verificare VM eșuată: $case" }
}
```

QEMU este extras cu 7-Zip din arhiva fixată în `config/sources.lock.json`; instalatorul EXE **nu este executat**. Scriptul cere 7-Zip existent și nu îl instalează. Sursa Windows este legată din [pagina oficială QEMU](https://www.qemu.org/download/#windows), iar checksumul public este la [weilnetz](https://qemu.weilnetz.de/w64/qemu-w64-setup-20260811.sha512). Firmware-ul este cel inclus în arhiva QEMU; configurația Secure Boot folosește [SMM și perechea CODE/VARS documentate de QEMU](https://github.com/qemu/qemu/blob/master/pc-bios/descriptors/50-edk2-x86_64-secure.json).

virt-firmware 26.10 declară o dependență POSIX `crypt_r` care nu se compilează pe Windows. Instalarea cu `--no-deps` este intenționată și limitată mediului VM separat: funcțiile de varstore EFI folosite aici nu folosesc criptarea parolelor POSIX. Dependențele necesare sunt fixate separat. `pip check` nu va considera acest mediu complet pentru toate funcțiile virt-firmware. setuptools 80.9.0 păstrează pkg_resources necesar pyfatfs/fs. Certificatul ASUS existent are serial zero și produce un avertisment cryptography; nu îl modificăm și nu ocolim verificarea Secure Boot.

Fișierele fiecărui test sunt în `build/vm-lab/<caz>-<timestamp>/`: result.json, qemu-command.json, debug.log, serial.log și, pentru cazurile care rămân la ecran, screen.png. În lipsa MOK sau la handoff, timeoutul închide VM după ecranul așteptat. Un timeout singur nu este considerat succes: evaluatorul cere mesajele concrete de respingere sau ecranul Windows cu BCD lipsă. Rezumatul selectează doar cele șase rulări finale și verifică hashul PROBE față de buildul curent.

Limitări

Nu sunt demonstrate: politica/SBAT specifică ASUS, înrolarea fizică MOK, PCR-uri TPM, proprietatea GOP NVIDIA/AMD în preboot, citirea PROM NVIDIA, execuția FWSEC/V67, driverul NVIDIA 580.97 după FLR, stabilitatea sau câștigul de performanță. Acestea necesită etape fizice distincte, aprobate conform [TESTING.md](TESTING.md). Nu se copiază VM-HARNESS.EFI pe USB-ul laptopului.
