> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Compilarea variantei automate interne

Toate comenzile de aici scriu numai fișiere de proiect. Nu instalează pe partiții, nu înrolează MOK și nu modifică ordinea reală de boot. Compilatorul portabil și dependențele fixate sunt cele din README; checkoutul upstream trebuie să rămână la commitul din `config/sources.lock.json`, fără modificări.

Folosește un director nou pentru fiecare build; nu suprascrie executabilul al cărui hash a fost aprobat:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/build.py --board config/board.reviewed.json --output build/automatic-NEW --automatic
.\.venv\Scripts\python.exe -X utf8 tools/test.py --build-root build/automatic-NEW
.\.venv\Scripts\python.exe -X utf8 tools/test_capture_transaction.py --evidence results/physical-capture-20261025-201848 --build-root build/automatic-NEW --output-name saved-board-tests
.\.venv-vm\Scripts\python.exe -X utf8 tools/test_automatic_vm.py --image build/automatic-NEW/M6501-AUTOMATIC.EFI
.\.venv\Scripts\python.exe -X utf8 tools/stage_internal.py --build-root build/automatic-NEW --output build/internal-release-NEW
```

Mediul `.venv-vm` este separat de benchmark și conține dependențele QEMU/OVMF din [VM-LAB.md](VM-LAB.md). VM folosește numai fișiere locale de disc și varstore; nu atașează hardware-ul laptopului. Ea verifică sursa SSD, logarea privată, Secure Boot și ramura de respingere/încărcare Windows, nu execuția GPU.

`--automatic` produce un executabil suplimentar, `M6501-AUTOMATIC.EFI`, cu `MODE_UNLOCK` și `M6501_AUTOMATIC`. `uefi/automatic_boot.h` implementează temporizarea și predicatele de anulare sigură. `tools/build.py` generează separat IO-ul automat din sursa upstream fixată: director privat `\EFI\M6501GPU\RTX-UNLOCK`, loguri fără suprascriere RUN0000–RUN9999, sursă internă GPT ESP acceptată. La epuizarea spațiului sau sloturilor, nu se activează GPU-ul; este necesară administrarea logurilor.

Nucleul SS0-only și activele NVIDIA rămân fixate. ROM-ul original nu este inclus în pachet; hashul lui este încorporat și ROM-ul live se verifică la pornire. Un build într-un alt director poate avea alt hash PE, inclusiv din cauza căilor incluse în diagnostice. Recompilarea cere verificare și o nouă autorizare MOK; nu presupune că hashul candidatului publicat aici va coincide.

Instalarea este separată de compilare. `Install-InternalAutomatic.ps1` cere fișierul de acord al planului exact și validează identitatea discului/E:, dimensiunile, zona liberă după shrink, pachetul și helperii înainte de prima modificare a partiției. `Disable-InternalAutomatic.ps1` restaurează ordinea UEFI fără ștergerea partiției de date sau a MOK.
