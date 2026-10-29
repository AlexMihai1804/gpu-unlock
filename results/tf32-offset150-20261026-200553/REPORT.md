> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Comparație offset GPU 0 MHz / +150 MHz

**Performanță/corectitudine: PASS. Verificare hardware finală: CU AVERTISMENT.** Unlock-ul FP16/BF16/TF32 a rămas activ. „Stock” în acest raport înseamnă offset GPU zero, cu unlock păstrat.

Aceeași pornire, aceleași biblioteci și matrice dense 8192×8192. Ordine: **0 → +150 → +150 → 0 MHz**; fiecare rundă acoperă FP16, BF16, TF32 și FP32. Încălzire 6 s/mod, 7 probe × 30 GEMM/mod/rundă. Valorile de mai jos provin din mediana celor 14 timpi CUDA per configurație și mod.

| Mod | Offset 0, TFLOPS | Offset +150, TFLOPS | Câștig | Control 0 final vs inițial |
|---|---:|---:|---:|---:|
| FP16 | 40.975 | 43.509 | +6.19% | -2.06% |
| BF16 | 42.552 | 44.679 | +5.00% | -1.54% |
| TF32 | 22.285 | 23.637 | +6.07% | -1.04% |
| FP32 | 8.835 | 9.316 | +5.45% | -0.08% |

## Rulări individuale

| Rundă | Offset MHz | Mod | TFLOPS | Putere mediană activă, W | SM median, MHz | Max. °C |
|---|---:|---|---:|---:|---:|---:|
| 1 | 0 | FP16 | 41.528 | 118.43 | 1402 | 72 |
| 1 | 0 | BF16 | 42.918 | 119.49 | 1447 | 74 |
| 1 | 0 | TF32 | 22.355 | 119.75 | 1507 | 77 |
| 1 | 0 | FP32 | 8.838 | 118.98 | 1470 | 82 |
| 2 | 150 | FP16 | 43.513 | 114.87 | 1447 | 78 |
| 2 | 150 | BF16 | 44.637 | 117.20 | 1500 | 78 |
| 2 | 150 | TF32 | 23.606 | 119.19 | 1597 | 80 |
| 2 | 150 | FP32 | 9.265 | 118.77 | 1537 | 83 |
| 3 | 150 | FP16 | 43.507 | 119.44 | 1470 | 80 |
| 3 | 150 | BF16 | 44.767 | 119.68 | 1515 | 79 |
| 3 | 150 | TF32 | 23.653 | 119.76 | 1597 | 80 |
| 3 | 150 | FP32 | 9.332 | 119.70 | 1560 | 82 |
| 4 | 0 | FP16 | 40.674 | 119.69 | 1380 | 80 |
| 4 | 0 | BF16 | 42.258 | 119.72 | 1425 | 79 |
| 4 | 0 | TF32 | 22.123 | 119.52 | 1500 | 80 |
| 4 | 0 | FP32 | 8.831 | 119.74 | 1470 | 82 |

Temperatura maximă în toate eșantioanele: **83°C**. Niciun prag artificial de oprire la temperatură.

Puterea și frecvența sunt mediane din telemetria cu utilizare GPU ≥90%, incluzând încălzirea. Nu reprezintă energia exactă a probelor CUDA sau consumul laptopului la priză. Ordinea ABBA reduce influența unei derive simple, dar nu garantează temperaturi, Dynamic Boost sau limite de putere perfect identice.

## Limitări raportate de NVIDIA

- Offset 0 MHz, 717 eșantioane active: Power Cap 97.91%; SW Thermal 0.00%; HW Thermal 0.00%; HW Power Brake 0.00%.
- Offset 150 MHz, 699 eșantioane active: Power Cap 96.85%; SW Thermal 0.29%; HW Thermal 0.00%; HW Power Brake 0.00%.

Procentele reprezintă eșantioane, nu împărțirea exactă a timpului CUDA.

## Eveniment hardware după comparație

Evenimente în intervalul celor patru runde: 0; în întreaga fereastră verificată: 1.

- 2026-10-26T18:16:05.0187968Z: Microsoft-Windows-WHEA-Logger 17, dispozitiv PCI\VEN_1022&DEV_14B8&SUBSYS_14531022&REV_00; status corectabil 0x1000, necorectabil 0x0.

Ultima setare și citire 0 MHz: 2026-10-26T18:13:34.380368+00:00. Finalul comparației: 2026-10-26T18:15:29.966662+00:00. Inițializarea controlului final: 2026-10-26T18:16:07.359107+00:00.

Evenimentul a apărut la 150.6 s după ultima setare zero și la 35.1 s după finalul comparației. Topologia PnP confirmă că portul 1022:14B8, 00:01.1 este părintele RTX 3060. Nu este avertismentul cunoscut al portului de rețea. Nu putem stabili mai precis starea GPU în fereastra dintre sfârșitul comparației și inițializarea controlului final.

Aceeași semnătură apare în 5 înregistrări istorice anterioare testelor de offset. Cauza nu este demonstrată; evenimentul rămâne în filtrul de sănătate. Dovezi: `pcie-warning-review.json`, `gpu-pcie-topology.json`, `health-after.json` și `historical-gpu-pcie-events.json`.

**Câștigul măsurat nu oferă un verdict de stabilitate hardware complet curat. +150 MHz nu este aplicat permanent.**

## Corectitudine și restaurare

Toate cele 16 rezultate complete de mod/rundă sunt verificate prin SHA256 față de stock-ul original în precizia respectivă, plus 2.048 de valori comparate cu CPU FP64. Fiecare rezultat este ieșirea finală a unei runde; rezultatele intermediare nu sunt inspectate individual.

Offseturile grafice și de memorie au revenit la zero, verificate de procesul principal, de watchdog și printr-o citire independentă. Benchmarkul final la zero păstrează profilul FP16/BF16/TF32 deblocat. Secure Boot rămâne activ în aceeași pornire. Nu s-au modificat tensiuni, limita de putere, memoria, firmware-ul sau configurația de boot; nu este aplicat un profil permanent.

Date și verificări: `comparison-review.json`, `comparison-summary.json`, `round-0.json` … `round-3.json`, `telemetry.jsonl`, `offset-events.jsonl`, `watchdog-result.json`, `independent-final-inventory.json`, `before.json`, `after.json` și `source/`.

Acest test arată câștigul în GEMM pentru condițiile măsurate; nu certifică stabilitatea în toate aplicațiile sau după sleep/resume. Stock-ul original fără unlock rămâne o măsurare istorică separată în `../baseline-2026-10-25.json`.
