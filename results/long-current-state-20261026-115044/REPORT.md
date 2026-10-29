> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Test FP16/BF16 fără restart: oprit

Durată efectivă: **3 min 24 s**, cu pauze termice; timp CUDA măsurat **2.78 minute** (81.7% din durată).
Motivul opririi: **Stopped by local STOP marker**. Temperatura maximă: 87.0°C. **Durata planificată nu a fost completată; nu se acordă PASS pentru durata completă.**

| Mod | TFLOPS mediană în blocurile active | P5–P95 | Ultimul vs primul sfert |
|---|---:|---:|---:|
| FP16 | 26.048 | 24.490–40.771 | +54.80% |
| BF16 | 27.585 | 26.328–41.909 | +49.30% |

Au fost efectuate 4500 GEMM, în 45 blocuri. Toate verificările numerice: **PASS**. Hashurile acoperă ultima ieșire completă din fiecare bloc; cele 2.048 de elemente CPU FP64/bloc au trecut verificarea.
Erori Display/nvlddmkm în această pornire: **0**. Evenimente hardware neașteptate noi în timpul testului: **0**. Evenimente anterioare testului: **0**. Avertismentele corectate cunoscute ale portului de rețea în această pornire: 0.
Pauze de răcire: 0; timp în pauze: 0.00 minute.

Avertismente WHEA 17 corectate, anterioare testului, pe root port-ul AMD 1022:14b8, 00:01.1, din amonte de GPU: **0**. Nu sunt asimilate avertismentului cunoscut de rețea. Cauza lor nu este stabilită; detaliile și momentele sunt în review.json.

Benchmarkul scurt inițial nu prezintă profilul de performanță deblocat. Rezultatul măsoară sesiunea existentă de după standby. Nu s-a executat o deblocare nouă și nu s-a făcut restart.
Secure Boot din Windows: 1 înainte și după. Nu s-au modificat driverul, limita de putere, frecvențele, firmware-ul, cheile sau ordinea de boot. Exportul firmware/MOK anterior rămâne o verificare la momentul său.

Benchmarkul scurt final a fost omis după oprirea termică. Datele brute și hashurile dovezilor sunt în review.json și endurance/.
