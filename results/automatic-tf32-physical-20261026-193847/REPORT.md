> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# FP16/BF16/TF32: deblocare fizică verificată

**PASS pentru această pornire și pentru validarea TF32 de 5 minute.** RUN0000 a scris SS0 `0x88888888` și SS1 `0x8`, a confirmat ambele valori după un singur FLR și a predat Windows cu zero mapări DMA rămase și accesul PCI restaurat. Windows a pornit prin Boot0006 la **26 octombrie 2026, 19:36:35 București**.

SecureBoot=1, SetupMode=0, validare shim activă. Noul hash automat este prezent în MOK, toate hashurile MOK anterioare sunt păstrate, iar PK/KEK/db/dbx sunt identice cu exportul de dinaintea actualizării. Boot0000 și Windows Boot Manager Boot0001 sunt identice la nivel de octeți. Nu s-a făcut flash BIOS/VBIOS.

## Benchmark scurt, același cuBLAS și aceleași intrări

Matrice dense 8192×8192, acumulare și ieșire FP32, mediane de 5×10 multiplicări după 4 s de încălzire pe mod. GPU la offset zero; biblioteci, driver, configurație, intrări și hashuri complete comparate automat.

| Mod | Stock, TFLOPS | SS0-only recent | SS0+SS1 acum | Față de stock | Față de SS0-only recent |
|---|---:|---:|---:|---:|---:|
| FP16 | 27,204 | 41,945 | 42,039 | +54,53% | +0,22% |
| BF16 | 27,694 | 43,251 | 45,076 | +62,77% | +4,22% |
| TF32 | 13,865 | 13,537 | **23,467** | **+69,25%** | **+73,35%** |
| FP32 | 9,343 | 9,021 | 9,326 | −0,18% | +3,38% |

Toate cele patru ieșiri complete sunt identice cu stock, fiecare în propriul mod de precizie. TF32 nu este comparat bit cu bit cu modul FP32. Verificările numerice CPU FP64 pe 2.048 de valori/mod au trecut.

Telemetria activă pe fază susține creșterea TF32 de la aproximativ 7,55 la **14,83 TFLOPS/GHz**, aproximativ 1,97×. Ceasul median TF32 a fost 1.582 MHz și puterea mediană 119,215 W; originalul stock era aproximativ 1.837 MHz și 119,62 W. Aceste observații sunt compatibile cu debit total sub 2×, în ciuda randamentului pe frecvență aproape dublu. Normalizarea este grosieră, include încălzirea și nu reprezintă un contor IPC sau citirea selectorilor în Windows. Diferențele mici FP16/BF16 dintre cele două porniri nu sunt atribuite exclusiv SS1.

Date: `../tf32-after-automatic-20261026-1938.json`, referința SS0-only `../tf32-before-automatic-20261026-1926.json` și stock `../baseline-2026-10-25.json`. Verificare: `physical-tf32-review.json` și `performance-state.json`.

## Validare susținută TF32

**300,685 s de fereastră de sarcină, 286,462 s CUDA măsurat, 95,27% timp CUDA.** Au fost executate **5.900 GEMM-uri în 59 blocuri**. Ieșirea finală a fiecărui bloc a fost verificată integral prin SHA256 față de stock și pe 2.048 de valori față de CPU FP64. Toate verificările au trecut. Rezultatele intermediare dintre verificări nu sunt inspectate individual.

- TF32 mediană: **22,551 TFLOPS**; P5–P95: **22,287–23,197 TFLOPS**.
- Ultimul sfert față de primul: **−2,89%**, pe măsură ce condițiile termice/de putere au evoluat. Nu prezentăm această rundă ca lipsită de derivă.
- Maximum: **85°C**. Niciun prag artificial sau pauză termică impusă.
- În 260 de eșantioane cu utilizare GPU ≥90%: **SW Power Cap 99,62%**; SW/HW Thermal Slowdown, HW Slowdown și HW Power Brake **0%**.
- Putere mediană în eșantioanele active: **116,705 W**.
- Zero evenimente noi de driver/hardware în intervalul sarcinii. Avertismentul WHEA 17 corectat pe portul de rețea, deja cunoscut, a apărut înaintea benchmarkului; nu este o eroare GPU nouă.

Procentele limitărilor sunt proporții ale eșantioanelor, nu atribuirea exactă a timpului CUDA. Limita dominantă observată rămâne puterea. Nu există o măsurare stock de aceeași durată și temperatură; mediana susținută nu este folosită pentru un procent suplimentar de câștig comparabil.

Surse: `tf32-endurance/summary.json`, `tf32-endurance/blocks.jsonl`, `tf32-endurance/telemetry.jsonl`, `tf32-endurance/health.jsonl` și `tf32-endurance-analysis.json`.

## Pornirea implicită și starea finală

La colectare, BootCurrent era 6, dar ordinea de boot devenise **1,0,6**, diferită de cea verificată la instalare. Cauza reordonării nu este demonstrată. Ordinea a fost readusă la **6,0,1**, verificată prin readback, fără modificarea vreunei intrări, a cheilor sau a fișierelor. Dovezi în `../gpu-boot-priority-20261026-194442/`. Nu a fost efectuată o repornire suplimentară pentru verificarea persistenței ordinii.

Noua variantă este configurată prima; vechea deblocare automată și Windows Boot Manager sunt păstrate. Nu este necesar USB și nu este necesară o nouă înrolare MOK pentru aceeași imagine.

Citirea independentă de la final confirmă offseturile GPU la zero. Windows este în aceeași pornire, Secure Boot în registry este 1. Evaluatorul de performanță a fost adaptat să recunoască TF32 la rată mărită; vechea presupunere că TF32 trebuie să rămână la viteza stock nu mai respinge această configurație. Au trecut testele pentru tranzacții incomplete, rezumatele TF32, clasificarea cu TF32 accelerat și regresiile modurilor anterioare.

Rezultatul validează această placă/driver și sarcina GEMM testată în această pornire. Persistența după alte porniri, D3cold sau sleep/resume și stabilitatea în toate aplicațiile rămân în afara acestei măsurători.
