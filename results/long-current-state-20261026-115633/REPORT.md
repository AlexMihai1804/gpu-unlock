> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Test lung FP16/BF16

Rezultat: **PASS**.

Scop: Performance profile after user restart; continuous workload.
Profil de performanță deblocat înainte și după: DA.
Regim: continuous; timp CUDA: 92.0% din durată; pauze termice: 0.
Durată: 20.04 minute; timp CUDA măsurat: 18.44 minute.
Temperatura maximă: 85°C. Blocuri cu verificarea întregii ieșiri: 416.

| Mod | TFLOPS mediană | TFLOPS P5–P95 | Ultimul vs primul sfert |
|---|---:|---:|---:|
| FP16 | 40.705 | 40.239–41.661 | +1.59% |
| BF16 | 41.887 | 41.575–42.682 | +1.02% |

Limitări raportate de NVIDIA, în eșantioanele cu utilizare GPU ≥90%:

- Putere: 98.33% din eșantioane.
- Limitare termică software: 0.00%; hardware: 0.00%.
- Power brake hardware: 0.00%.
Procentele descriu eșantioane de telemetrie, nu o împărțire exactă a timpului CUDA.
Limita de putere curentă observată în snapshoturi: 110.80–117.93 W; mediană 113.29 W.

Datele brute și verificările sunt în review.json, before.json, after.json și endurance/.

Rezultatul acoperă GEMM dens cu intrări fixe și această pornire; nu certifică toate aplicațiile sau persistența după sleep/resume.
