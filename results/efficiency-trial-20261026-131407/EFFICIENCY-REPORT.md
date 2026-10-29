> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Eficiență FP16/BF16 și reglaj temporar

Stare: **passed**. Verificări complete: **PASS**.

Energia este diferența contorului NVML, în aceeași fereastră care încadrează GEMM-urile măsurate. Copierea și verificarea ieșirii se fac după citirea finală a energiei. TFLOP/J are aceeași dimensiune ca TFLOPS/W.

Contorul descrie GPU-ul, inclusiv orice altă activitate simultană; nu măsoară consumul laptopului la priză.

| Etapă | Mod | TFLOPS CUDA | W medii din energie | TFLOP/J | MHz mediană | mV mediană | Max. °C |
|---|---|---:|---:|---:|---:|---:|---:|
| reference-0 | FP16 | 40.965 | 117.78 | 0.3478 | 1394 | 721.88 | 76 |
| reference-0 | BF16 | 42.310 | 117.86 | 0.3589 | 1436 | 734.38 | 78 |
| trial-30 | FP16 | 40.653 | 116.01 | 0.3504 | 1384 | 712.50 | 80 |
| trial-30 | BF16 | 42.286 | 118.00 | 0.3582 | 1442 | 725.00 | 80 |
| reference-1 | FP16 | 40.090 | 117.84 | 0.3402 | 1361 | 712.50 | 81 |
| reference-1 | BF16 | 41.472 | 117.63 | 0.3525 | 1408 | 726.56 | 82 |
| trial-60 | FP16 | 41.008 | 117.46 | 0.3491 | 1387 | 706.25 | 82 |
| trial-60 | BF16 | 42.103 | 117.16 | 0.3593 | 1432 | 718.75 | 83 |
| reference-2 | FP16 | 39.873 | 117.27 | 0.3400 | 1354 | 709.38 | 83 |
| reference-2 | BF16 | 41.316 | 118.18 | 0.3494 | 1406 | 725.00 | 83 |

GEMM-uri măsurate: 8,000. Blocuri verificate: 20.

Offseturile +30/+60 MHz modifică relația frecvență/tensiune; nu sunt o tensiune fixă sau un undervolt certificat. Nu se scriu tensiuni, limite de putere, frecvențe VRAM, firmware sau setări de pornire.

Restaurare/verificare finală a offseturilor: True.

O îmbunătățire este doar candidat pentru testare lungă dacă depășește ambele referințe vecine cu peste 1%, cu puterea în ±3% și temperatura maximă în ±3°C. Acest criteriu este un filtru practic, nu o analiză de semnificație statistică.

Curba exportată folosește o interfață privată numai pentru citire. Sunt capturate primele 80 de puncte; nu este garantat că acestea formează curba completă. Curba poate varia cu temperatura.

Referința de aici este un test scurt, cu GPU mai rece decât în testul de 20 de minute. Diferența de TFLOPS față de testul lung nu reprezintă un câștig de reglaj.

Niciun profil suplimentar de reglaj nu a fost instalat pentru aplicare automată.

+30 MHz, FP16: eficiență față de referințele vecine +0.75%, +3.00%; candidat pentru test lung: NU.

+30 MHz, BF16: eficiență față de referințele vecine -0.19%, +1.63%; candidat pentru test lung: NU.

+60 MHz, FP16: eficiență față de referințele vecine +2.62%, +2.68%; candidat pentru test lung: DA.

+60 MHz, BF16: eficiență față de referințele vecine +1.94%, +2.83%; candidat pentru test lung: DA.
