> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Concluzia testului cu offset temporar

**PASS. Offsetul +60 MHz este un candidat pentru validare lungă. Setarea finală este din nou 0 MHz.**

Testul a folosit secvența 0 / +30 / 0 / +60 / 0 MHz. Comparația de mai jos folosește cele două referințe vecine ale etapei +60 MHz, la temperaturi apropiate. Ratele sunt calculate din lucrul total, timpul CUDA și energia totală ale blocurilor respective.

| Mod | Referințe vecine, TFLOPS | +60 MHz, TFLOPS | Câștig debit | Câștig TFLOP/J |
|---|---:|---:|---:|---:|
| FP16 | 39,981 | 41,008 | +2,57% | +2,65% |
| BF16 | 41,394 | 42,103 | +1,71% | +2,38% |

Puterea medie măsurată din energie a fost 117,55 → 117,46 W pentru FP16 și 117,91 → 117,16 W pentru BF16. Limita de putere nu a fost schimbată de test. Valorile sunt raportate de GPU; nu reprezintă consumul laptopului la priză.

Offsetul +30 MHz nu a demonstrat un avantaj consecvent față de ambele referințe vecine. La +60 MHz, câștigul de eficiență a fost pozitiv față de fiecare referință separat: FP16 +2,62…+2,68%; BF16 +1,94…+2,83%. Această singură secvență scurtă nu stabilește semnificația statistică sau stabilitatea pe termen lung.

Au fost măsurate 8.000 de GEMM-uri în 20 de blocuri. Ieșirea finală a fiecărui bloc a fost verificată integral prin SHA256 față de referința inițială și prin 2.048 de valori CPU FP64; toate verificările au trecut. Nu se pretinde verificarea fiecărui rezultat intermediar.

Temperatura maximă din telemetrie a fost **83°C**. În eșantioanele active din ferestrele măsurate ale etapei +60 MHz, limitarea de putere a fost activă în 100%, iar limitarea termică software/hardware și power brake în 0%. Procentele descriu eșantioane de telemetrie, nu o împărțire exactă a timpului CUDA.

Nu au apărut evenimente noi Display/nvlddmkm/WHEA sau de suspendare în intervalul verificat. Pornirea Windows a rămas aceeași, iar starea Secure Boot din registry a rămas 1.

Restaurarea normală a offseturilor inițiale GPU și VRAM a fost verificată de procesul principal, procesul separat de supraveghere și o citire independentă finală. A fost validată restaurarea normală pe hardware; intervenția watchdog-ului la o blocare nu a fost provocată în acest test.

Nu s-a instalat un profil suplimentar de reglaj aplicat automat. Nu s-au modificat BIOS/VBIOS, chei Secure Boot, Windows Boot Manager, tensiuni fixe, limita de putere sau offseturi VRAM. Deblocarea Tensor Core existentă a rămas separată de acest experiment.

Pasul necesar înaintea unui profil permanent este validarea candidatului +60 MHz în sarcină lungă, la temperatură stabilizată și cu aceleași verificări numerice. Datele de aici susțin un câștig mic de eficiență; nu demonstrează încă un undervolt certificat pentru toate aplicațiile.

Date: `neighbor-comparison.json`, `phase-limiters.json`, `energy-blocks.jsonl`, `energy-telemetry.jsonl`, `efficiency-review.json`, `independent-final-readback.json`, `watchdog-result.json`, `health-after.json`. Codul executat este arhivat în `source/` și identificat prin hashuri.
