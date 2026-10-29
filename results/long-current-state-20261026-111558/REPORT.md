> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Test FP16/BF16 fără restart: oprit la pragul termic

Durată efectivă: **16 min 28 s**, cu pauze termice; timp CUDA măsurat **7.45 minute** (45.3% din durată).
Motivul opririi: **82°C**, pragul ales pentru test. **Cele 20 de minute nu au fost completate; nu se acordă PASS pentru durata completă.**

| Mod | TFLOPS mediană în blocurile active | P5–P95 | Ultimul vs primul sfert |
|---|---:|---:|---:|
| FP16 | 21.807 | 18.173–22.189 | +0.31% |
| BF16 | 22.358 | 18.468–22.657 | -12.43% |

Au fost efectuate 8425 GEMM, în 337 blocuri. Toate verificările numerice: **PASS**. Hashurile acoperă ultima ieșire completă din fiecare bloc; cele 2.048 de elemente CPU FP64/bloc au trecut verificarea.
Erori Display/nvlddmkm în această pornire: **0**. Evenimente hardware neașteptate noi în timpul testului: **0**. Evenimente anterioare testului: **5**. Avertismentele corectate cunoscute ale portului de rețea în această pornire: 1.
Pauze de răcire: 150; timp în pauze: 7.52 minute.

Avertismente WHEA 17 corectate, anterioare testului, pe root port-ul AMD 1022:14b8, 00:01.1, din amonte de GPU: **5**. Nu sunt asimilate avertismentului cunoscut de rețea. Cauza lor nu este stabilită; detaliile și momentele sunt în review.json.

Benchmarkul scurt inițial nu prezintă profilul de performanță deblocat. Rezultatul măsoară sesiunea existentă de după standby. Nu s-a executat o deblocare nouă și nu s-a făcut restart.
Secure Boot din Windows: 1 înainte și după. Nu s-au modificat driverul, limita de putere, frecvențele, firmware-ul, cheile sau ordinea de boot. Exportul firmware/MOK anterior rămâne o verificare la momentul său.

Benchmarkul scurt final a fost omis după oprirea termică. Datele brute și hashurile dovezilor sunt în review.json și endurance/.
