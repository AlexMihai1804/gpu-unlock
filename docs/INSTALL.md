# Instalare, compilare, utilizare și recuperare

Ghidul descrie copia publică a laboratorului pentru ASUS M6501RM.313. Instalarea mediului Python și compilarea sunt reproductibile din surse. **Instalarea fizică a unlock-ului cere capturi, verificări și un profil nou pentru calculatorul propriu.** Repository-ul nu conține un pachet EFI gata de instalat sau planurile private ale laptopului original.

Documentele cu prefixul „Arhivă” păstrează etapele cercetării. Formulări precum „instalat”, „autorizat”, „MOK deja înrolat” și numerele Boot0000/Boot0006 din ele descriu exclusiv experimentul original.

## 1. Cerințe

- Windows x64, Python 3.13 x64 și Git în PATH.
- GPU și driver NVIDIA funcționale pentru benchmark; mediul fizic testat este în [README](../README.md).
- Alimentator conectat, profil ASUS consecvent și răcire adecvată pentru măsurători comparabile.
- Pentru pașii UEFI: potrivire completă cu identitatea adaptorului, acces la meniul de boot și Windows Boot Manager funcțional.
- Pentru o instalare proprie: backup al datelor și al configurației de boot; dacă sistemul folosește BitLocker, cheia sa de recuperare trebuie să fie disponibilă înaintea schimbărilor de boot.

Dependențele nu necesită instalare globală CUDA, Windows SDK sau WSL. Driverul 580.97 este versiunea testată, nu o instrucțiune de downgrade.

## 2. Clonează și pregătește mediul

```powershell
git clone https://github.com/AlexMihai1804/gpu-unlock.git
Set-Location gpu-unlock
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r bench/requirements.txt -r tools/requirements.txt
New-Item -ItemType Directory -Force results | Out-Null
nvidia-smi
```

Comenzile folosesc direct Python din `.venv`; activarea mediului nu este necesară. Dacă `py` nu este disponibil, folosește calea interpreterului Python 3.13 x64. Nu publica directoarele locale `.venv`, `build`, `vendor` sau noile rezultate fără revizuire.

## 3. Măsoară referința înaintea modificărilor

După o pornire normală prin Windows Boot Manager:

```powershell
.\.venv\Scripts\python.exe -X utf8 bench/gemm.py --label stock-local --output results/stock-local.json
```

Implicit: 8192×8192, 4 s încălzire pe mod, 5 probe × 10 GEMM, cronometrare CUDA, acumulare și ieșire FP32. Se verifică valorile finite, hashul întregii ieșiri și 2.048 de elemente față de CPU FP64. O rulare mică pentru verificarea mediului poate folosi `--n 1024`.

Fișierul JSON conține timpi, precizie, configurație și telemetrie. Benchmarkul măsoară starea deja existentă a GPU-ului; nu efectuează deblocare.

## 4. Pregătește sursele și compilează

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/prepare.py bootstrap
.\.venv\Scripts\python.exe -X utf8 tools/prepare.py shim
.\.venv\Scripts\python.exe -X utf8 tools/prepare.py firmware
.\.venv\Scripts\python.exe -X utf8 tools/build.py
.\.venv\Scripts\python.exe -X utf8 tools/test.py
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s bench -p "test_*.py" -v
```

`bootstrap` descarcă checkout-urile fixate și compilatorul portabil; `shim` extrage shim/MokManager semnate din pachetele fixate; `firmware` extrage și verifică activele NVIDIA fără executarea instalatoarelor. Toate rămân în directoarele proiectului. Orice diferență de hash sau sursă modificată oprește pregătirea.

`tools/test.py` cere buildul, shim și activele firmware deja pregătite. Testele native folosesc un ROM sintetic și servicii UEFI simulate; nu accesează GPU-ul fizic. Unele teste care cer dovezi fizice nepublicate pot fi omise explicit. Laboratorul QEMU/OVMF este opțional și are dependențe suplimentare descrise în [VM-LAB.md](VM-LAB.md).

| Imagine implicită | Rol |
|---|---|
| `build/M6501-PROBE.EFI` | Identitate și trust; fără MMIO GPU |
| `build/M6501-HANDOFF.EFI` | Verificări și pornirea Windows existent, fără unlock |
| `build/M6501-CAPTURE.EFI` | Captură PROM/stare după confirmarea din aplicație; poate activa temporar PCI MEMORY |
| `build/M6501-UNLOCK-CANDIDATE.EFI` | Candidat cu deblocarea blocată prin profilul public |

## 5. Profilul propriu și validarea fizică

Această etapă presupune revizuirea codului UEFI și a datelor proprii. Nu copia GUID-urile exemplu sau valorile unui alt laptop. Refuzul unui control trebuie investigat; nu elimina verificările pentru a forța pornirea.

1. **Inventar numai prin citire.** Din PowerShell Administrator, în directorul proiectului:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Collect-ReadOnly.ps1
   Get-Partition | Where-Object IsSystem | Format-List DiskNumber,PartitionNumber,Guid,Size
   ```

   Colectorul salvează date locale, inclusiv identificatori, trust și inventarul de boot. Păstrează exporturile private. Verifică SecureBoot=1, SetupMode=0 și politica efectivă db/dbx/SBAT. Compatibilitatea shim depinde de politica sistemului la momentul testului; pachetele fixate nu garantează acceptarea pe orice firmware.

2. **PROBE → HANDOFF → CAPTURE**, pe un USB FAT32 separat, cu verificarea fiecărei etape înaintea următoarei. Pentru HANDOFF, copiază profilul pending în `config/board.local.json`, înlocuiește `windows_partition` cu GUID-ul ESP propriu, păstrează `evidence_reviewed=false` și reconstruiește:

   ```powershell
   Copy-Item config/board.pending.json config/board.local.json
   # Editează board.local.json cu GUID-ul propriu, înaintea compilării.
   .\.venv\Scripts\python.exe -X utf8 tools/build.py --board config/board.local.json
   .\.venv\Scripts\python.exe -X utf8 tools/stage_usb.py --mode probe --output build/USB-PROBE-LOCAL
   ```

   `stage_usb.py` creează numai un folder local nou. Pentru etapele următoare folosește `--mode handoff`, respectiv `--mode capture`, cu directoare de ieșire noi. Copierea pe USB este un pas separat; identifică discul și nu suprascrie ESP Windows.

   Boot prin meniul temporar ASUS. La prima lansare, aplicația neînrolată trebuie respinsă; MokManager poate oferi **Enroll hash from disk** pentru `EFI/BOOT/grubx64.efi`. Acesta este executabilul proiectului, nu GRUB. Înrolarea modifică persistent lista MOK; fiecare executabil recompilat are propriul hash. Hashul PE/Authenticode MOK diferă de SHA-256 al întregului fișier. Nu dezactiva Secure Boot sau validarea shim pentru a continua.

   După PROBE verifică identitatea exactă și GOP AMD. După HANDOFF verifică pornirea Windows, trustul și benchmarkul de control. După CAPTURE verifică ROM-ul complet, restaurarea PCI și logul. [Procedura detaliată istorică](TESTING.md) explică formatul logurilor; unele verificatoare folosesc nume de rulări și căi din laboratorul original și trebuie adaptate datelor proprii.

3. **Analizează captura proprie.** Exemplu pentru un ROM deja salvat:

   ```powershell
   .\.venv\Scripts\python.exe -X utf8 tools/inspect_rom.py .\roms\original.ROM
   Get-FileHash -Algorithm SHA256 .\roms\original.ROM
   ```

   Parserul verifică structura recunoscută, nu autenticitatea sau siguranța execuției. Dovezile trebuie să lege identitatea plăcii, hashul întregului PROM, chipul, fuse-urile, BAR-urile, memoria rezervată, proprietarii PCI, starea DMA și recuperarea după FLR. Nu completa o captură scurtă cu zerouri și nu folosi ROM-ul altui dispozitiv.

4. **Creează un profil revizuit local**, pornind din `config/board.reviewed.example.json`. Setează `windows_partition`, `chip`, `prom_sha256`, `booter_fuse_raw` și `fwsec_fuse_raw` din propriile dovezi; `evidence_reviewed=true` se setează numai după verificare. `tools/build.py` impune identitatea exactă și fuse-urile acceptate de acest adaptor. Fișierul `config/board.reviewed.json` este exclus din Git.

5. **Compilează un candidat separat.** Comenzile următoare pregătesc imagini locale; nu le instalează:

   ```powershell
   # SS0-only: FP16/BF16, SS1 păstrat.
   .\.venv\Scripts\python.exe -X utf8 tools/build.py --board config/board.reviewed.json --output build/ss0-local

   # Candidat manual separat SS0+SS1: include experimentul TF32.
   .\.venv\Scripts\python.exe -X utf8 tools/build.py --board config/board.reviewed.json --output build/ss1-local --ss1-full-experiment
   ```

   Fiecare director trebuie să fie nou. Pentru tranzacțiile pe capturi salvate există `tools/test_capture_transaction.py`; acestea cer structura proprie de dovezi și rapoartele de trust. Simularea nu validează tranzacția pe hardware. Începe fizic cu o singură încercare manuală revizuită și verifică logul, restaurarea PCI/DMA și handoff-ul înaintea oricărei automatizări.

**Pornirea automată pe SSD:** `--automatic` și `--automatic-ss1-experiment` sunt variante explicite de compilare. Scripturile `Install-*`, `Deploy-Authorized*`, `Complete-*` și verificatoarele asociate păstrează logica experimentului original, inclusiv topologia discurilor și planuri cu hashuri. GUID-urile și serialele au fost înlocuite cu substituenți. Aceste scripturi necesită adaptare și o revizuire completă înainte de utilizare pe alt sistem; nu există o comandă publică universală de instalare. Nu genera fișiere de autorizare fictive și nu reutiliza rapoarte anonimizate ca dovezi ale calculatorului propriu.

## 6. Compară performanța după un boot verificat

```powershell
.\.venv\Scripts\python.exe -X utf8 bench/gemm.py --label unlock-local --output results/unlock-local.json
.\.venv\Scripts\python.exe -X utf8 bench/compare.py results/stock-local.json results/unlock-local.json
```

Păstrează aceleași biblioteci, intrări, alimentare, profil și offseturi. Comparatorul respinge configurații diferite și verificări numerice eșuate. Verifică și temperatura, puterea, evenimentele Display/nvlddmkm/WHEA și un control de revenire la boot normal.

Pentru 20 de minute FP16/BF16, folosind **propria** referință:

```powershell
New-Item -ItemType Directory results/endurance-local | Out-Null
.\.venv\Scripts\python.exe -X utf8 bench/endurance.py --seconds 1200 --baseline results/stock-local.json --output-directory results/endurance-local
```

Poți adăuga `--temperature-limit 82` pentru un prag ales explicit; implicit nu există prag artificial. Ctrl+C sau fișierul `STOP` în directorul rulării solicită oprirea la următoarea verificare. Hashul verifică ieșirea finală a fiecărui bloc, nu toate rezultatele intermediare. Un PASS nu certifică alte aplicații sau sleep/resume.

`bench/upstream_gemm.py` cere separat un mediu PyTorch CUDA compatibil. Mediul măsurat a avut PyTorch 2.8.0+cu126; acesta nu este instalat de requirements-ul cuBLAS. Folosește interpreterul propriului mediu și un director nou existent sub `results/`.

Antrenarea opțională cere PyTorch/torchvision, un checkpoint ResNet50 compatibil și CIFAR-100 local. Setează `$env:CIFAR100_PROJECT` la directorul ce conține `day_5/best_resnet50_cifar100_88_09.pth` și `cifar/`. Pentru runnerul +150, `$env:GPU_UNLOCK_TORCH_PYTHON` poate indica interpreterul acelui mediu. Datasetul și checkpointurile nu sunt distribuite. Scripturile de tuning și `activate150.py` modifică offseturi; utilizarea lor este separată de benchmarkul simplu.

## 7. Revenire și diagnostic

- Pentru testul USB: oprește complet laptopul, scoate USB-ul și selectează **Windows Boot Manager** din meniul ASUS. Verifică din nou referința. După un eșec de tranzacție/DMA, nu relansa imaginea în același ciclu de alimentare.
- Pentru o instalare automată proprie revizuită: **Esc** în numărătoarea de 5 s sare peste unlock. Alegerea Windows Boot Manager evită ruta proiectului. Scripturile de rollback cer dovezile exacte ale instalării respective; o copie proaspătă a repository-ului nu le conține.
- Scoaterea USB-ului sau alegerea Windows Boot Manager nu șterge intrarea MOK. Eliminarea ei trebuie să vizeze exact intrarea proiectului, păstrând celelalte chei. Nu reseta PK/KEK/db/dbx sau TPM pentru a elimina aplicația.
- `SHA256 mismatch`: oprește-te și verifică sursa/cache-ul; nu elimina controlul de hash.
- `Board identity differs` sau candidat blocat: verifică compatibilitatea și dovezile profilului; nu modifica identificatorii pentru a pretinde compatibilitate.
- Shim refuzat: verifică semnătura și politicile dbx/SBAT curente. Nu înlocui cu un shim vulnerabil pentru a ocoli politica.
- Pierdere de performanță după standby: colectează starea și măsoară separat după un boot complet. Persistența după resume rămâne o limită cunoscută a experimentului.

La raportarea unei probleme include model/BIOS, PCI/subsystem, driver, comanda folosită și logul relevant revizuit. Elimină serialele, UUID-urile, numele calculatorului, căile personale și datele de recuperare înaintea publicării.
