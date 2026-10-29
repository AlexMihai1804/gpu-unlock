# GPU unlock — ASUS M6501RM / RTX 3060 Laptop

Laborator UEFI și Windows pentru deblocarea debitului Tensor Core FP16, BF16 și TF32 pe **ASUS M6501RM, BIOS M6501RM.313, RTX 3060 Laptop GA106 A1**, cu Secure Boot activ. Include surse, compilare cu dependențe fixate, teste și rezultate măsurate.

**[Instrucțiuni de instalare, compilare și utilizare](docs/INSTALL.md)** · [Rezultate publicate](results/README.md) · [Verificarea publicării](docs/VALIDATION.md) · [Licențe](THIRD_PARTY_NOTICES.md)

This is a board-specific UEFI research project for the ASUS M6501RM / RTX 3060 Laptop, with Windows benchmarks and Secure Boot validation. The public default profile disables unlocking. Documentation and measurement reports are primarily in Romanian.

## Compatibilitate

| Componentă | Configurație testată |
|---|---|
| Laptop / BIOS | ASUS M6501RM / M6501RM.313 |
| GPU | RTX 3060 Laptop, GA106 A1, 6 GiB |
| PCI / subsystem / revizie | `10de:2520` / `1043:1313` / `a1` |
| BDF / VBIOS | `0000:01:00.0` / `94.06.38.00.38` |
| Afișare UEFI | GOP AMD `1002:1681` |
| Sistem / driver testat | Windows x64 / NVIDIA 580.97 |
| Trust | SecureBoot=1, SetupMode=0, shim cu validare activă și MOK |

Adaptorul verifică identitatea plăcii, ROM-ul, fuse-urile și starea PCI înaintea tranzacției. Alte modele, versiuni BIOS, drivere și situații de afișare nu sunt validate. Acesta este un proiect experimental: o tranzacție UEFI greșită poate bloca pornirea și poate necesita recuperare.

Profilul public `config/board.pending.json` are `evidence_reviewed=false`. GUID-urile de disc/partiție și serialul USB din sursele publice sunt **substituenți**, iar profilul original verificat este exclus. Compilarea implicită păstrează deblocarea blocată. Instalatoarele istorice cer planuri și dovezi locale care nu sunt distribuite.

## Rezultate măsurate

Benchmark scurt cu cuBLAS, matrice dense 8192×8192, acumulare și ieșire FP32, offset GPU zero:

| Mod | Stock, TFLOPS | SS0+SS1, TFLOPS | Diferență observată |
|---|---:|---:|---:|
| FP16 | 27,204 | 42,039 | +54,53% |
| BF16 | 27,694 | 45,076 | +62,77% |
| TF32 | 13,865 | 23,467 | +69,25% |
| FP32, control | 9,343 | 9,326 | −0,18% |

Hashurile întregii ieșiri au fost identice cu stock în fiecare precizie. [Raportul fizic](results/automatic-tf32-physical-20261026-193847/REPORT.md) documentează configurația, puterea, verificările și limitele comparației. Rezultatele sunt observații pe acest laptop; diferențele dintre porniri nu izolează toate efectele termice și de alimentare.

- **FP16/BF16, 20 de minute, SS0-only:** mediane 40,705 / 41,887 TFLOPS, maximum 85°C, 416 ieșiri finale de bloc verificate; [raport](results/long-current-state-20261026-115633/REPORT.md).
- **TF32, 5 minute, SS0+SS1:** mediană 22,551 TFLOPS, maximum 85°C, 59 ieșiri finale de bloc verificate; [raport](results/automatic-tf32-physical-20261026-193847/REPORT.md).
- **Protocol PyTorch, 29 octombrie 2026, unlock +150 MHz:** două rulări, FP16 43,991 / 43,154, BF16 45,178 / 44,358 și TF32 23,603 / 23,416 TFLOPS; [raport separat](results/upstream-gemm-20261029-104056/REPORT.md). Acesta include un offset de frecvență și nu este o comparație stock/unlock.

Persistența după sleep/resume, D3cold și stabilitatea tuturor aplicațiilor nu sunt certificate. Benchmarkurile nu aplică unlock-ul. Sarcinile de GEMM și antrenare pot avea comportamente diferite.

## Pornire rapidă: benchmark în Windows

Din PowerShell, cu Python 3.13 x64, Git și driver NVIDIA funcțional:

```powershell
git clone https://github.com/AlexMihai1804/gpu-unlock.git
Set-Location gpu-unlock
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r bench/requirements.txt -r tools/requirements.txt
New-Item -ItemType Directory -Force results | Out-Null
.\.venv\Scripts\python.exe -X utf8 bench/gemm.py --label local-baseline --output results/local-baseline.json
```

Această comandă măsoară FP16, BF16, TF32 și FP32 în starea curentă. Nu schimbă firmware-ul, configurația de boot, frecvențele sau limita de putere. Nu necesită PyTorch sau un CUDA Toolkit complet. Pachetele NVIDIA se descarcă în mediul Python local.

## Compilare și teste locale

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/prepare.py bootstrap
.\.venv\Scripts\python.exe -X utf8 tools/prepare.py shim
.\.venv\Scripts\python.exe -X utf8 tools/prepare.py firmware
.\.venv\Scripts\python.exe -X utf8 tools/build.py
.\.venv\Scripts\python.exe -X utf8 tools/test.py
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s bench -p "test_*.py" -v
```

Aceste comenzi pregătesc fișiere și rulează teste pe calculator. Nu pornesc imagini EFI, nu instalează pe USB/discuri și nu înrolează MOK. Descărcările sunt verificate față de [sursele fixate](config/sources.lock.json). Păstrează suficient spațiu pentru arhive, compilator și firmware.

Compilarea produce PROBE, HANDOFF, CAPTURE și un candidat blocat în `build/`. Pentru configurația proprie și etapele fizice, urmează [ghidul complet](docs/INSTALL.md).

## Structură și proveniență

| Director | Conținut |
|---|---|
| `uefi/` | Adaptor ASUS, verificări, handoff Windows și numărătoarea pornirii automate |
| `tools/` | Pregătire, compilare, verificări offline, pachete locale și laborator VM |
| `bench/` | GEMM cuBLAS/PyTorch, endurance, telemetrie și experimente de eficiență |
| `tests/` | Teste Python/C și servicii UEFI simulate |
| `config/` | Dependențe fixate și profile publice fără dovezi de deblocare |
| `docs/` | Ghidul actual și arhiva investigațiilor |
| `results/` | Rapoarte și un set selectat de măsurători anonimizate |

Tranzacția GPU provine din [craftingmod/rtx30-unlock](https://github.com/craftingmod/rtx30-unlock), cu originea în [Zagitta/gpu-unlock](https://github.com/Zagitta/gpu-unlock). Adaptarea locală oferă SS0-only, cu SS1 păstrat, și variante separate SS0+SS1. Reviziile exacte sunt în lockfile. Firmware-ul nu este flash-uit în BIOS/VBIOS de aplicație.

Codul este **GPL-2.0-only**, conform [LICENSE](LICENSE) și [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Firmware-ul NVIDIA, shim și celelalte dependențe au condiții proprii. Copia publică exclude ROM-uri, executabile EFI, chei, exporturi brute UEFI și checkpointuri de antrenare. [Politica datelor publicate](results/README.md) explică anonimizarea și limitele verificării arhivei.
