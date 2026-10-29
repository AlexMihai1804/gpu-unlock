> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Primul unlock fizic v3: reușit cu Secure Boot activ

La 25 octombrie 2026, prima încercare autorizată pe ASUS M6501RM.313 / RTX 3060 Laptop 2520 A1 / subsystem 1043:1313 a încheiat tranzacția și a pornit Windows 11 cu driverul **580.97**. Benchmarkul din acel boot a arătat accelerare FP16/BF16, cu ieșiri complete identice la nivel de hash cu referința.

**Acesta este un rezultat pentru un singur boot experimental și un GEMM controlat.** Ulterior a trecut și [revenirea la referință după oprire completă și boot normal](NORMAL-RETURN-RESULT-v3.md). Repetabilitatea pe alte booturi experimentale, sleep/resume și stabilitatea aplicațiilor reale rămân de verificat. Accelerarea nu s-a păstrat în bootul normal A2 testat.

## Rezultatele măsurate

Aceeași configurație cuBLAS, driver, GPU, biblioteci și intrări: GEMM 8192³, FP32 pentru acumulare/ieșire, reducere de precizie intermediară interzisă, 4 secunde încălzire/mod și 5×10 iterații. Comparatorul a verificat egalitatea mediului și hashurile intrărilor.

| Mod | Referință TFLOPS | După unlock TFLOPS | Câștig throughput |
|---|---:|---:|---:|
| FP16 | 27,204 | **42,710** | **+57,00%** |
| BF16 | 27,694 | **44,726** | **+61,50%** |
| TF32 | 13,865 | 13,829 | −0,26% |
| FP32 | 9,343 | 9,347 | +0,04% |

Toate cele patru verificări numerice au trecut, toate ieșirile au fost finite, iar SHA-256 al întregii ieșiri coincide cu referința în fiecare mod. Verificarea numerică CPU FP64 acoperă 2048 elemente/mod; egalitatea hashului complet față de referință este o verificare suplimentară. Aceste probe nu demonstrează corectitudinea tuturor aplicațiilor.

Fișiere brute: `results/baseline-2026-10-25.json` și `results/unlock-v3-B1-2026-10-25.json`. Nu s-au schimbat driverul, frecvențele sau limitele de putere pentru acest test. Telemetria nvidia-smi este păstrată; valorile sale sunt eșantioane aproximative care includ încălzirea, nu măsurători de energie sau TGP exact sincronizate cu GEMM. În eșantioanele active, temperaturile maxime au fost 66°C FP16 / 67°C BF16, față de 67°C / 68°C în referință. Clockurile SM au fost mai mici în modurile accelerate, deci nu este presupusă egalitatea frecvențelor.

## Tranzacție și restaurare

Dovezi arhivate, cu recitire SHA-256: `results/physical-unlock-20261025-212306/`. Logul `RTX-UNLOCK/RUN06/UNLOCK.TXT` arată:

- identitate exactă, SecureBoot=1/SetupMode=0 și GOP AMD independent;
- ROM live identic cu originalul, fuse și toate cele cinci assets acceptate;
- FWSEC a fost observat rulând, apoi oprit; scratch=0 și WPR2 în intervalul calculat;
- **SS0=0x88888888; SS1=3 păstrat fără scriere**;
- **un singur FLR**, GFW complet, SEC2 reset eliberat, GSP oprit, WPR2 dezactivat pentru driver;
- `TRANSACTION result=0 contained=0 FLRs=1 maps=0 retained=0 quiesced=1 fault=0`;
- `MEM_RESTORE status=0 confirmed=1 command=0` și handoff către Windows Boot Manager existent.

Windows a pornit la **21:21:11, ora Bucureștiului**, în același boot al tentativei. Candidatul exact este SHA-256 `f716f8827c38a63b353fd28ad505bb2e7713991fb152df6b34a250c89bd08336`; hash MOK `5dca60a7602255a01ff4f7771aacac62100afda4138f9235d0476f9b48f68642`.

## Secure Boot și starea Windows

Exportul administrativ de după unlock, `results/uefi-post-unlock-20261025-212307/`, confirmă SecureBoot=1, SetupMode=0, validare shim activă, noul hash în MokListRT și păstrarea hashurilor MOK anterioare. **PK/KEK/db/dbx și intrarea Windows Boot Manager sunt identice cu exportul inițial; Windows Boot Manager rămâne primul.** Lista MOK a fost modificată persistent prin înrolarea autorizată; aceasta nu este prezentată drept lipsă a oricărei modificări de trust.

După benchmark nu sunt evenimente Display/nvlddmkm în bootul curent. Este prezent un avertisment WHEA 17 corectat pe portul Realtek `00:02.1 / 1022:14ba`, cu UncorrectableErrorStatus=0. Același tip a fost reprodus anterior și la boot normal fără USB; cauza sa rămâne neconfirmată. Nu există alte evenimente WHEA în colectarea de după benchmark.

Nu s-a făcut flash BIOS/VBIOS, înlocuire Windows Boot Manager sau instalare de driver modificat. Modificările GPU au fost efectuate în RAM/configurația temporară a dispozitivului. Durata persistenței selectorilor după idle sau suspend nu este încă măsurată.

## Ce urmează

Acordul pentru **o singură încercare** a fost folosit. Nu este autorizată automat o repetare a tranzacției. Stickul conține în continuare candidatul, iar celelalte loguri/ROM-ul sunt păstrate.

Controlul de [pornire normală fără USB](NORMAL-RETURN-RESULT-v3.md) a trecut în A2, cu abatere maximă 0,76% de la referință și ieșiri identice. Urmează, numai după acord nou, [planul cu încă două încercări B2/B3](REPRODUCIBILITY-v3-PLAN.md) și controalele normale aferente. Un al doilea benchmark în același boot ar verifica numai acea sesiune, nu repetabilitatea între booturi.

Analiza poate fi refăcută fără acces la GPU sau firmware:

```powershell
.\.venv\Scripts\python.exe tools/review_unlock.py --evidence results/physical-unlock-20261025-212306 --post results/uefi-post-unlock-20261025-212307 --benchmark results/unlock-v3-B1-2026-10-25.json
.\.venv\Scripts\python.exe bench/compare.py results/baseline-2026-10-25.json results/unlock-v3-B1-2026-10-25.json
```
