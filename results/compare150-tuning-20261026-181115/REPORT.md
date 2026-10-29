> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Test adaptiv al offsetului GPU

Execuție: **PASS**. Stare: passed.

Candidat susținut de validarea lungă: **+150 MHz**.

| Etapă | Offset MHz | Mod | TFLOPS | TFLOP/J | W medii | Max. °C | CUDA s |
|---|---:|---|---:|---:|---:|---:|---:|
| warmup-0 | 0 | FP16 | 40.676 | 0.3417 | 118.99 | 82 | 97.3 |
| warmup-0 | 0 | BF16 | 42.010 | 0.3536 | 118.78 | 81 | 83.8 |
| reference-0 | 0 | FP16 | 40.214 | 0.3380 | 118.96 | 83 | 54.7 |
| reference-0 | 0 | BF16 | 41.574 | 0.3496 | 118.89 | 83 | 42.3 |
| trial-120 | 120 | FP16 | 42.455 | 0.3577 | 118.65 | 84 | 62.2 |
| trial-120 | 120 | BF16 | 43.578 | 0.3653 | 119.24 | 84 | 60.6 |
| reference-1 | 0 | FP16 | 40.081 | 0.3365 | 119.08 | 84 | 54.9 |
| reference-1 | 0 | BF16 | 41.313 | 0.3483 | 118.59 | 84 | 42.6 |
| trial-150 | 150 | FP16 | 42.864 | 0.3610 | 118.71 | 84 | 61.6 |
| trial-150 | 150 | BF16 | 44.011 | 0.3696 | 119.05 | 84 | 60.0 |
| reference-2 | 0 | FP16 | 40.028 | 0.3370 | 118.76 | 84 | 54.9 |
| reference-2 | 0 | BF16 | 41.360 | 0.3464 | 119.37 | 85 | 42.5 |
| validation-150 | 150 | FP16 | 42.589 | 0.3602 | 118.21 | 86 | 309.8 |
| validation-150 | 150 | BF16 | 43.762 | 0.3705 | 118.09 | 86 | 291.4 |
| reference-final | 0 | FP16 | 39.606 | 0.3363 | 117.77 | 87 | 66.6 |
| reference-final | 0 | BF16 | 40.751 | 0.3462 | 117.67 | 87 | 54.0 |

Blocuri măsurate/verificate: 138; GEMM-uri: 55,200; temperatură maximă: 87°C.

Se verifică ieșirea finală integrală a fiecărui bloc și 2.048 de valori CPU FP64, nu toate rezultatele intermediare.

Energia este diferența contorului GPU pentru aceeași fereastră care încadrează GEMM-urile; copierea și validarea CPU sunt excluse. Nu este consumul laptopului la priză.

Fiecare creștere cere un câștig de eficiență >1% și de debit >0,5% față de fiecare referință vecină, pentru ambele moduri. Puterea trebuie să fie în ±3%, iar temperatura maximă în ±3°C. Pentru următorul pas se cere și un câștig marginal >0,5% în ambele moduri. Acestea sunt filtre practice, nu teste de semnificație statistică. Nu există prag artificial de oprire la temperatură.

Restaurarea offseturilor inițiale: True. Niciun profil suplimentar nu este aplicat la pornire.

+120 MHz: merită în comparația cu 0 MHz: True; progresie justificată față de pasul precedent: True.
- FP16: eficiență +6.07%; față de fiecare control [5.838084999878679, 6.307474245983125]; câștig marginal None%.
- BF16: eficiență +4.69%; față de fiecare control [4.484774792522606, 4.8911255036986345]; câștig marginal None%.

+150 MHz: merită în comparația cu 0 MHz: True; progresie justificată față de pasul precedent: True.
- FP16: eficiență +7.20%; față de fiecare control [7.288158616696139, 7.121229096362036]; câștig marginal 1.0671109380011812%.
- BF16: eficiență +6.40%; față de fiecare control [6.120485380351215, 6.687972135281939]; câștig marginal 1.6394232643563766%.

Validarea de 10 minute CUDA, față de referințele vecine:

- FP16: 42.589 TFLOPS, eficiență +7.01%, ultimul vs primul sfert -1.10%.
- BF16: 43.762 TFLOPS, eficiență +6.97%, ultimul vs primul sfert -0.77%.

Rezultatul nu certifică toate aplicațiile, persistența după suspendare sau un undervolt universal. Nu se modifică tensiuni fixe, limita de putere, VRAM, firmware sau cheia de încredere Secure Boot.
