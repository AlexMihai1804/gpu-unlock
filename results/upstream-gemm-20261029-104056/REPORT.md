> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# gpu-unlock: protocol GEMM pe RTX 3060 Laptop

**PASS — două rulări complete, la unlock +150 MHz.** Benchmarkul nu a pornit antrenări și nu a schimbat setările GPU. Citirea independentă finală confirmă +150 MHz pe domeniul grafic și 0 MHz pe memorie. Secure Boot este activ în registry, în aceeași pornire Windows.

Am reprodus protocolul publicat pentru RTX 3060 Laptop în [gpu-unlock #53](https://github.com/Zagitta/gpu-unlock/issues/53): matrice dense **8192×8192**, acumulare FP32, **20 s încălzire pe fiecare mod**, **5 probe × 20 multiplicări**, mediana timpilor CUDA și **două rulări complete**. FP32 este martorul. Durata măsurată a întregii ferestre, inclusiv verificări: **209,66 s**.

| Mod | Rularea 1, TFLOPS | Rularea 2, TFLOPS | Rularea 2 față de 1 |
|---|---:|---:|---:|
| FP16 | 43,991 | 43,154 | −1,90% |
| BF16 | 45,178 | 44,358 | −1,82% |
| TF32 | 23,603 | 23,416 | −0,79% |
| FP32 | 9,352 | 9,305 | −0,50% |

Mediul rămâne cel instalat: **Windows, PyTorch 2.8.0+cu126**, driver NVIDIA 580.97. Raportul sursă folosește Linux și PyTorch 2.14.1+cu130; este reprodus protocolul de măsurare, nu întregul său mediu software sau limita de 80 W a celuilalt laptop. Raportul sursă nu specifică tipul ieșirii; aici am ales explicit **ieșire FP32**, documentată în datele brute.

## Precizie și verificări

`allow_fp16_reduced_precision_reduction`, `allow_bf16_reduced_precision_reduction` și `allow_fp16_accumulation` sunt toate `False`. TF32 este permis doar pentru rândul TF32. Benchmarkul folosește `torch.mm` în `inference_mode`, cu buffere de ieșire prealocate și evenimente CUDA pentru cronometrare.

Toate cele opt rezultate complete sunt finite. Fiecare rezultat a trecut verificarea a 2.048 de valori față de CPU FP64, folosind intrările cuantizate efectiv. Cele două rulări au intrări identice și **același SHA256 al întregii ieșiri pentru fiecare precizie**. Aceasta este identitate între repetări în același mod, nu identitate între FP16, BF16, TF32 și FP32 sau față de un GPU blocat.

## Temperatură, putere și sănătate

- Temperatură maximă: **83°C**. Nu a fost folosit un prag artificial de oprire la temperatură.
- Putere mediană în eșantioanele active: **119,609 W**. Limita de putere raportată a variat între **106,7 și 120,0 W**; benchmarkul nu a modificat-o.
- În **387 de eșantioane cu utilizare GPU ≥90%**: Power Cap **99,74%**, SW Thermal **0%**, HW Thermal **0%**, HW Power Brake **0%**.
- **Zero evenimente noi Display/nvlddmkm/WHEA sau de suspendare** în fereastra verificată.
- **Zero erori de citire a telemetriei** în această rulare.

Procentele descriu eșantioane, nu atribuirea exactă a timpului CUDA. Limitarea dominantă observată este puterea. Diferențele de până la 1,9% între rundele complete sunt raportate, fără o afirmație de semnificație statistică sau de stabilitate în toate aplicațiile.

## Ce compară testul

Recomandarea oficială de raportare cere [același benchmark și aceeași limită de putere înainte/după](https://github.com/Zagitta/gpu-unlock/blob/7eb51bccae0a0b7e599e084d971170e9a1e82d0c/.github/ISSUE_TEMPLATE/unlock-failure.yml). Testul de față validează **starea curentă unlock +150**. Nu am repornit fără unlock și nu există o referință stock nouă măsurată prin exact acest protocol. Valorile stock mai vechi, obținute prin altă implementare și cu alte durate de încălzire, nu sunt folosite pentru un procent nou de câștig.

Script: `source/upstream_gemm.py`. Date și audit: `summary.json`, `review.json`, `telemetry.jsonl`, `health-final.json`, `offsets-before.json`, `offsets-after.json`, `independent-offsets-final.json`, `context-before.json`, `context-after.json` și `upstream-provenance.json`.
