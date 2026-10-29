> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Investigație TF32 — 26 octombrie 2026

**Diagnostic Windows: PASS. Pregătire candidat: PASS. Accelerare TF32 pe laptop: încă nevalidată.**

TF32 rulează deja pe traseul Tensor Core cuBLAS observat prin CUPTI (`cutlass_80_tensorop_s1688gemm...`). Setările matematice 16, 0 și 19 folosesc același kernel, cu **13,451 / 13,482 / 13,483 TFLOPS**. Repetarea inițială: 13,417 TFLOPS. Toate ieșirile complete TF32 coincid cu stock, iar verificările numerice au trecut. Maximum 67°C; fără evenimente noi de driver/hardware în intervalul verificat; offseturile GPU/VRAM au rămas identice, GPU la 0 MHz. Secure Boot în registry: 1.

Diagnosticul exclude dezactivarea simplă a TF32 și efectul setărilor math-mode testate ca explicații ale lipsei accelerării. Nu exclude toate efectele de selecție/implementare cuBLAS sau inițializare ale driverului. Telemetria de frecvență pe fază nu este sincronizată exact cu timpul CUDA; prima fază FP16 include pornirea GPU și nu este folosită pentru a deduce randamentul per ciclu.

**SS1 este ipoteza pregătită pentru test:** configurația actuală păstrează SS1=3; candidatul scrie SS1=8, păstrând SS0=88888888. Rapoarte primare pe GA106 Linux și Windows arată accelerare TF32 cu ambii selectori. Alte plăci/versiuni nu demonstrează compatibilitatea acestui ASUS sau o corespondență universală SS1–TF32.

Candidatul separat a trecut 22 scenarii de tranzacție și 14 cazuri preflight simulate pe ROM-ul salvat. Regresia SS0 a trecut 43 teste Python și nouă grupuri native; nucleul SS0 rămâne identic cu cel automat validat. Imaginea experimentală reală a trecut shim/MOK într-o VM cu Secure Boot, NVMe și refuzul lipsei GPU-ului înainte de scrieri. VM-ul nu validează efectul pe GPU sau driverul ASUS real.

Imagine: `build/tf32-ss1-20261026-v4/M6501-TF32-SS1-CANDIDATE.EFI`.

SHA256 fișier: `517c38d22a8d4c31ac0f9c168efbb2d984128d8e3ac08082e43177edbdcaf25c`.

Hash PE pentru MOK: `4c98895062ce71acf4f117e7a2b63176a8e528d545a72e39f97d446866803198`.

Pachetul intern este pregătit sub `build/release-tf32-20261026-v4/INTERNAL-CANDIDATE/`, separat în `EFI/M6501TF32`. Nu necesită USB permanent sau o nouă partiție. **Nu a fost instalat, înrolat sau aplicat; nu s-a înlocuit pornirea automată actuală.**

Sunt necesare acordul pentru noul hash MOK și o pornire experimentală manuală. Apoi comparăm patru moduri cu SS0-only, la offset 0 și condiții apropiate. Nu promitem dublarea TF32 înaintea acestei măsurători.

[Cod, build, surse și protocol](../../docs/TF32-INVESTIGATION.md). [Verificările candidatului](candidate-ready.json). Diagnosticul brut și sănătatea driverului sunt în `../tf32-diagnostic-20261026-185622/`; sursele externe consultate sunt arhivate în `sources/`.
