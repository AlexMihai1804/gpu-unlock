# Verificarea copiei publice — 29 octombrie 2026

Copia publică a fost compilată și testată separat de directorul operațional al laptopului, pe Windows x64 cu Python 3.13. Au fost folosite sursele fixate și cache-urile locale ale compilatorului, shim și firmware; nu s-a repetat descărcarea tuturor dependențelor într-un sistem Windows gol.

| Verificare | Rezultat |
|---|---|
| Compilare PROBE, HANDOFF, CAPTURE și candidat blocat | PASS |
| Teste Python din `tests/` | 51 / 51 PASS |
| Teste Python din `bench/` | 46 / 46 PASS |
| Verificări native adaptor | 53 PASS |
| Numărătoare automată și fallback | 217 PASS |
| Verificări native PCI | 255 PASS |
| Transport PCI/DMA și tratarea erorilor | PASS |
| Verificări SHA-256 | 48 PASS |
| Scenarii nucleu real cu servicii UEFI simulate | 20 / 20 PASS |
| PROBE/HANDOFF/CAPTURE fără rutine GPU write/FLR/DMA în link map | PASS |
| Sintaxă Python și parsare JSON/JSONL publicate | PASS |

Comenzile principale sunt în [INSTALL.md](INSTALL.md). În pregătirea publicării nu au fost executate imagini EFI și nu au fost schimbate configurația de boot sau setările GPU. Rezultatele fizice din octombrie sunt dovezi istorice separate, descrise în [rapoarte](../results/README.md).

Profilele publice conțin GUID-uri substituent și `evidence_reviewed=false`. Imaginea compilată din configurația implicită rămâne blocată. Schimbarea identificatorilor și a căilor pentru publicare schimbă hashurile față de executabilele originale; hashurile MOK din arhivă nu autorizează o compilare nouă.
