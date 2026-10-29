> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Verdict: unlock funcțional, +120 MHz merită în GEMM-ul testat

**PASS. +120 MHz este cel mai bun offset dintre +60, +90 și +120 MHz testate. Offsetul suplimentar este acum restaurat la 0 MHz; nu s-a instalat un profil de reglaj aplicat automat.**

Controlul inițial și controlul final la 0 MHz corespund performanței Tensor Core deblocate. La final, randamentele pe frecvență FP16/BF16 sunt 0,992× / 0,994× din referința deblocată. Acest rezultat este o măsurare de performanță, nu o citire directă a selectorilor GPU.

## Validarea lungă la +120 MHz

Validarea a acumulat **605,70 secunde CUDA** în 627,95 secunde de fereastră de test, alternând FP16 și BF16. Comparația folosește controalele la 0 MHz de dinainte și de după, la temperaturi și puteri apropiate.

| Mod | Referințe 0 MHz, TFLOPS | +120 MHz, TFLOPS | Câștig debit | Câștig TFLOP/J |
|---|---:|---:|---:|---:|
| FP16 | 40,019 | 42,331 | +5,78% | +5,75% |
| BF16 | 41,289 | 43,381 | +5,07% | +4,89% |

Puterea GPU medie din contorul de energie a fost aproximativ **119 W** atât în controalele vecine, cât și la +120 MHz. Aplicația nu a modificat limita de putere. Eficiența măsurată la +120 a fost 0,3555 TFLOP/J FP16 și 0,3644 TFLOP/J BF16; acestea nu reprezintă consumul întregului laptop la priză.

Ultimul sfert față de primul: **+0,04% FP16 / +0,10% BF16**. Nu s-a observat degradarea debitului pe durata acestei validări.

## De ce am crescut offsetul

În etapele de selecție, câștigurile de eficiență față de controalele proprii au fost:

| Offset | FP16 | BF16 |
|---|---:|---:|
| +60 MHz | +2,72% | +2,10% |
| +90 MHz | +4,17% | +3,62% |
| +120 MHz | +5,60% | +4,75% |

Fiecare pas a trecut condițiile prestabilite, inclusiv câștigul marginal de peste 0,5% în ambele moduri. Acesta este cel mai bun rezultat din intervalul testat, nu o determinare a limitei de stabilitate sau a optimului global.

## Corectitudine, temperaturi și limitări

Întreaga rundă a măsurat **66.400 GEMM-uri în 166 de blocuri**, cu 1.746,71 secunde CUDA cumulate. Ieșirea finală a fiecărui bloc a fost verificată integral prin SHA256 și prin 2.048 de valori CPU FP64. Toate verificările au trecut. Nu se pretinde verificarea fiecărui rezultat intermediar.

Temperatura maximă a fost **86°C în întreaga telemetrie a rundei** și **85°C în blocurile validării lungi**. Nu a existat prag artificial de oprire la temperatură.

În cele 2.869 de eșantioane active din ferestrele măsurate ale validării lungi:

- SW Power Cap: **99,90%**.
- SW Thermal Slowdown: **0,10%**, trei eșantioane; deci limitarea termică software nu a fost complet absentă.
- HW Thermal Slowdown, HW Slowdown și HW Power Brake: **0%**.

Limitarea dominantă rămâne puterea. Procentele descriu eșantioane de telemetrie și nu o împărțire exactă a timpului CUDA. Temperatura hotspot/VRAM nu a fost stabilită prin acest test.

Nu au fost înregistrate evenimente noi Display/nvlddmkm/WHEA sau de suspendare în intervalul verificat. Pornirea Windows a rămas aceeași, iar Secure Boot din registry a rămas 1. Offseturile GPU/VRAM inițiale au fost verificate de procesul principal, watchdog și o citire independentă finală. Intervenția watchdog-ului la o blocare nu a fost provocată; a fost verificată restaurarea normală.

Rezultatul susține +120 MHz pentru acest GEMM dens și această pornire. Nu certifică toate aplicațiile, alte tipuri de încărcare, păstrarea după idle/suspendare sau un undervolt universal. Tensiunile fixe, limita de putere, VRAM, BIOS/VBIOS, cheile Secure Boot și configurarea pornirii nu au fost modificate de acest experiment.

În snapshotul de după test, fără proces CUDA raportat, cu 0% utilizare și 0 MiB alocați, driverul raporta P0, 1.425/7.001 MHz și aproximativ 28 W (`idle-after.csv`). Offseturile au fost confirmate la zero. Cauza acestei stări de repaus nu a fost stabilită; datele de acum nu demonstrează că a fost produsă de reglaj. Câștigul măsurat în sarcină nu trebuie extrapolat la economia zilnică a laptopului. Acest comportament de repaus trebuie verificat înaintea unui profil permanent.

Datele și verificările sunt în `adaptive-summary.json`, `adaptive-review.json`, `phase-limiters.json`, `energy-blocks.jsonl`, `energy-telemetry.jsonl`, `offset-events.jsonl`, `post-control-unlock.json` și `independent-final-readback.json`. Codul executat este arhivat în `source/`.
