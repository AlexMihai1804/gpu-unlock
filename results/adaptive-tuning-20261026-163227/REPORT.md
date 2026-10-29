> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Test adaptiv al offsetului GPU

Execuție: **PASS**. Stare: passed.

Candidat susținut de validarea lungă: **+120 MHz**.

| Etapă | Offset MHz | Mod | TFLOPS | TFLOP/J | W medii | Max. °C | CUDA s |
|---|---:|---|---:|---:|---:|---:|---:|
| warmup-0 | 0 | FP16 | 40.658 | 0.3428 | 118.58 | 81 | 97.4 |
| warmup-0 | 0 | BF16 | 42.011 | 0.3543 | 118.52 | 81 | 83.8 |
| reference-0 | 0 | FP16 | 40.004 | 0.3394 | 117.83 | 84 | 55.0 |
| reference-0 | 0 | BF16 | 41.129 | 0.3508 | 117.22 | 84 | 42.8 |
| trial-60 | 60 | FP16 | 40.992 | 0.3472 | 118.03 | 84 | 96.6 |
| trial-60 | 60 | BF16 | 42.183 | 0.3563 | 118.39 | 85 | 93.8 |
| reference-1 | 0 | FP16 | 39.887 | 0.3366 | 118.45 | 85 | 55.1 |
| reference-1 | 0 | BF16 | 41.154 | 0.3470 | 118.52 | 85 | 42.7 |
| trial-90 | 90 | FP16 | 41.686 | 0.3507 | 118.84 | 85 | 63.3 |
| trial-90 | 90 | BF16 | 42.791 | 0.3599 | 118.86 | 85 | 61.7 |
| reference-2 | 0 | FP16 | 39.812 | 0.3366 | 118.19 | 85 | 55.2 |
| reference-2 | 0 | BF16 | 40.982 | 0.3476 | 117.85 | 86 | 42.9 |
| trial-120 | 120 | FP16 | 42.270 | 0.3553 | 118.92 | 85 | 62.4 |
| trial-120 | 120 | BF16 | 43.317 | 0.3636 | 119.11 | 85 | 60.9 |
| reference-3 | 0 | FP16 | 40.012 | 0.3364 | 118.93 | 85 | 55.0 |
| reference-3 | 0 | BF16 | 41.259 | 0.3465 | 119.02 | 85 | 42.6 |
| validation-120 | 120 | FP16 | 42.331 | 0.3555 | 119.03 | 85 | 311.7 |
| validation-120 | 120 | BF16 | 43.381 | 0.3644 | 119.01 | 85 | 294.0 |
| reference-final | 0 | FP16 | 40.025 | 0.3361 | 119.06 | 85 | 65.9 |
| reference-final | 0 | BF16 | 41.309 | 0.3481 | 118.66 | 85 | 63.9 |

Blocuri măsurate/verificate: 166; GEMM-uri: 66,400; temperatură maximă: 86°C.

Se verifică ieșirea finală integrală a fiecărui bloc și 2.048 de valori CPU FP64, nu toate rezultatele intermediare.

Energia este diferența contorului GPU pentru aceeași fereastră care încadrează GEMM-urile; copierea și validarea CPU sunt excluse. Nu este consumul laptopului la priză.

Fiecare creștere cere un câștig de eficiență >1% și de debit >0,5% față de fiecare referință vecină, pentru ambele moduri. Puterea trebuie să fie în ±3%, iar temperatura maximă în ±3°C. Pentru următorul pas se cere și un câștig marginal >0,5% în ambele moduri. Acestea sunt filtre practice, nu teste de semnificație statistică. Nu există prag artificial de oprire la temperatură.

Restaurarea offseturilor inițiale: True. Niciun profil suplimentar nu este aplicat la pornire.

+60 MHz: merită în comparația cu 0 MHz: True; progresie justificată față de pasul precedent: True.
- FP16: eficiență +2.72%; față de fiecare control [2.2937823440125404, 3.145028637606795]; câștig marginal None%.
- BF16: eficiență +2.10%; față de fiecare control [1.5482053703346432, 2.6517786812417565]; câștig marginal None%.

+90 MHz: merită în comparația cu 0 MHz: True; progresie justificată față de pasul precedent: True.
- FP16: eficiență +4.17%; față de fiecare control [4.171360696873783, 4.175554824935013]; câștig marginal 1.415557521139288%.
- BF16: eficiență +3.62%; față de fiecare control [3.7089394622396687, 3.533175434636271]; câștig marginal 1.4897801581273074%.

+120 MHz: merită în comparația cu 0 MHz: True; progresie justificată față de pasul precedent: True.
- FP16: eficiență +5.60%; față de fiecare control [5.5591376289576555, 5.638009974715108]; câștig marginal 1.3680222117642415%.
- BF16: eficiență +4.75%; față de fiecare control [4.586557940417957, 4.917523220684439]; câștig marginal 1.0914607126799591%.

Validarea de 10 minute CUDA, față de referințele vecine:

- FP16: 42.331 TFLOPS, eficiență +5.75%, ultimul vs primul sfert +0.04%.
- BF16: 43.381 TFLOPS, eficiență +4.89%, ultimul vs primul sfert +0.10%.

Rezultatul nu certifică toate aplicațiile, persistența după suspendare sau un undervolt universal. Nu se modifică tensiuni fixe, limita de putere, VRAM, firmware sau cheia de încredere Secure Boot.
