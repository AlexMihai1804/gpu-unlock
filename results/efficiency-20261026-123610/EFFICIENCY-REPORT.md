> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Eficiență FP16/BF16 și reglaj temporar

Stare: **passed**. Verificări complete: **PASS**.

Sfera rezultatului: **referință energetică la setările existente; testul +30/+60 MHz nu a rulat**.

Cererea UAC pentru reglajul temporar a fost anulată. Niciun offset nu a fost aplicat.

Energia este diferența contorului NVML, în aceeași fereastră care încadrează GEMM-urile măsurate. Copierea și verificarea ieșirii se fac după citirea finală a energiei. TFLOP/J are aceeași dimensiune ca TFLOPS/W.

Contorul descrie GPU-ul, inclusiv orice altă activitate simultană; nu măsoară consumul laptopului la priză.

| Etapă | Mod | TFLOPS CUDA | W medii din energie | TFLOP/J | MHz mediană | mV mediană | Max. °C |
|---|---|---:|---:|---:|---:|---:|---:|
| reference-0 | FP16 | 42.616 | 117.25 | 0.3633 | 1447 | 710.94 | 74 |
| reference-0 | BF16 | 43.906 | 117.99 | 0.3721 | 1488 | 728.12 | 76 |

GEMM-uri măsurate: 1,600. Blocuri verificate: 4.

Offseturile +30/+60 MHz modifică relația frecvență/tensiune; nu sunt o tensiune fixă sau un undervolt certificat. Nu se scriu tensiuni, limite de putere, frecvențe VRAM, firmware sau setări de pornire.

Restaurare/verificare finală a offseturilor: True.

O îmbunătățire este doar candidat pentru testare lungă dacă depășește ambele referințe vecine cu peste 1%, cu puterea în ±3% și temperatura maximă în ±3°C. Acest criteriu este un filtru practic, nu o analiză de semnificație statistică.

Curba exportată folosește o interfață privată numai pentru citire. Sunt capturate primele 80 de puncte; nu este garantat că acestea formează curba completă. Curba poate varia cu temperatura.

Referința de aici este un test scurt, cu GPU mai rece decât în testul de 20 de minute. Diferența de TFLOPS față de testul lung nu reprezintă un câștig de reglaj.

Niciun profil suplimentar de reglaj nu a fost instalat pentru aplicare automată.
