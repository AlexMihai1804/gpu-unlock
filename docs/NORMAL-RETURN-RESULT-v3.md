> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Revenirea după unlock: control trecut

După oprirea conform pașilor și bootul Windows fără USB, confirmat de utilizator, performanța a revenit aproape de referință. Pornirea nouă este la 25 octombrie 2026, **21:34:10, ora Bucureștiului**. Stickul a fost reconectat la desktop. Nu au apărut loguri suplimentare, iar cele șapte loguri RUN00–RUN06 sunt identice cu arhiva precedentă.

| Mod | Normal A1 | Unlock B1 | Normal A2 după oprire |
|---|---:|---:|---:|
| FP16, TFLOPS | 27,204 | **42,710** | 26,998 |
| BF16, TFLOPS | 27,694 | **44,726** | 27,594 |
| TF32, TFLOPS | 13,865 | 13,829 | 13,814 |
| FP32, TFLOPS | 9,343 | 9,347 | 9,324 |

Abaterea A2 față de A1 este −0,76% FP16, −0,36% BF16, −0,37% TF32 și −0,20% FP32. Toate verificările numerice au trecut, toate ieșirile sunt finite, iar hashurile întregii ieșiri coincid cu A1 și B1. Driverul, GPU-ul, bibliotecile, mediul și parametrii GEMM au trecut comparația strictă. Nu s-au schimbat frecvențe sau limite de putere.

Această secvență A1 → B1 → A2 demonstrează accelerarea în bootul experimental și revenirea performanței în bootul normal testat. Nu demonstrează încă repetabilitatea pe mai multe booturi experimentale sau persistența după sleep/resume. Registrele selectorilor nu au fost citite direct din Windows; afirmația despre revenire se bazează pe benchmark și traseul de boot confirmat.

## Starea Windows și trustul

Exportul administrativ `results/uefi-normal-return-20261025-213640/` confirmă **SecureBoot=1, SetupMode=0**, PK/KEK/db/dbx identice și intrarea Windows Boot Manager identică/primă. În inventarul firmware nu mai apare intrarea temporară SanDisk, după bootul fără USB; nu pretindem că inventarul complet este identic și nu am executat comenzi de modificare BCD/BootOrder.

Variabilele runtime shim, inclusiv MokListRT, nu sunt expuse în acest boot direct. Aceasta nu dovedește ștergerea MOK-urilor persistente. Hashul candidatului fusese confirmat în MOK în bootul B1; nu am solicitat ștergerea cheilor sau înrolări noi.

După benchmark nu există evenimente Display/nvlddmkm. A fost observat același avertisment WHEA 17 corectat pe portul Realtek 00:02.1 / 1022:14ba, cu UncorrectableErrorStatus=0. Cauza sa rămâne neconfirmată; nu există alte evenimente WHEA în colectarea de control.

Compararea BCD a fost corectată pentru un newline terminal din ieșirea bcdedit atunci când Windows Boot Manager este ultimul bloc. Toate câmpurile și spațiile lor rămân comparate strict. Raportul inițial care a semnalat această diferență de formatare este păstrat; trei teste de regresie verifică și că o schimbare reală de cale este respinsă. Au trecut toate cele **21 de teste Python**. Codul și hashul executabilului UEFI rămân cele aprobate inițial.

## Dovezi și pasul următor

- Benchmark: `results/normal-return-A2-2026-10-25.json`.
- Dovezi: `results/normal-return-20261025-213601/`.
- Raport: `normal-return-review.json`; include hashurile logurilor, starea trustului și comparațiile A1/B1/A2.
- În acest boot nu a fost executat un unlock; acordul anterior pentru o încercare este consumat.

Pentru confirmarea repetabilității se poate aproba separat [planul cu încă două încercări](REPRODUCIBILITY-v3-PLAN.md), pe același candidat și același MOK, fără recompilare sau înlocuirea Windows Boot Manager. Planul nu este autorizat automat de acest rezultat.

Reproducerea analizei, fără acces hardware:

```powershell
.\.venv\Scripts\python.exe tools/review_normal_return.py --evidence results/normal-return-20261025-213601 --post results/uefi-normal-return-20261025-213640 --benchmark results/normal-return-A2-2026-10-25.json
```
