> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Sarcina continuă: oprită la pragul termic

Rulată fără restart, în Windows curent, pe 26 octombrie 2026. **Nu a completat cele 20 de minute.**

Sarcina s-a oprit automat la **82°C** după **99,516 secunde**, dintre care 94,676 secunde măsurate prin evenimente CUDA. Acesta este pragul prudent ales pentru test; raportul nu îl prezintă ca limită oficială sau ca eroare hardware.

Au fost validate 19 blocuri, 1.900 GEMM în total. Toate ieșirile complete au coincis cu referința, toate valorile au fost finite și verificările CPU FP64 au trecut.

| Mod | TFLOPS mediană | GEMM |
|---|---:|---:|
| FP16 | 21,697 | 1.000 |
| BF16 | 22,297 | 900 |

Nu a fost modificată limita de putere sau configurația GPU/Windows. Limita termică de 82°C este păstrată pentru continuarea cu pauze de răcire, în `results/long-current-state-20261026-111558/`. Cele două rulări au rapoarte separate; timpul primei încercări nu este numărat ca parte a celei de-a doua.
