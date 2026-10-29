> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# +150 MHz față de +120 MHz: câștig mic, test GEMM trecut

**PASS. +150 MHz aduce aproximativ încă 1% debit față de +120 MHz în comparația scurtă din aceeași rundă. A trecut și validarea de 10 minute CUDA. Offsetul final este restaurat la 0 MHz; nu s-a aplicat un profil permanent.**

## Comparația +120 / +150

| Mod | +120 MHz, TFLOPS | +150 MHz, TFLOPS | Câștig debit brut | Câștig marginal de eficiență normalizat |
|---|---:|---:|---:|---:|
| FP16 | 42,455 | 42,864 | +0,96% | +1,07% |
| BF16 | 43,578 | 44,011 | +0,99% | +1,64% |

Fiecare etapă a fost încadrată de referințe la 0 MHz. Câștigul marginal de eficiență compară raporturile fiecărui candidat la controalele proprii, pentru a limita influența variațiilor de putere și temperatură. Comparația directă dintre offseturi folosește etapele scurte de 120 secunde CUDA fiecare. Nu reprezintă două validări lungi, simultane sau identice termic. Pragurile practice prestabilite au fost trecute pentru ambele moduri.

## Validarea lungă la +150

Validarea a acumulat **601,25 secunde CUDA** în 624,70 secunde de fereastră de test, alternând cele două moduri.

| Mod | TFLOPS | Putere medie GPU | TFLOP/J | Câștig eficiență față de controalele vecine la 0 MHz | Ultimul vs primul sfert |
|---|---:|---:|---:|---:|---:|
| FP16 | 42,589 | 118,21 W | 0,3602 | +7,01% | −1,10% |
| BF16 | 43,762 | 118,09 W | 0,3705 | +6,97% | −0,77% |

Există o derivă descendentă mică a debitului în validare. Ea rămâne în pragul prestabilit de 3%, dar nu trebuie prezentată ca absență completă a degradării. Această rundă unică nu stabilește semnificația statistică sau stabilitatea în toate aplicațiile.

Întreaga rundă a măsurat **55.200 GEMM-uri în 138 de blocuri**, cu 1.439,05 secunde CUDA cumulate. Ieșirea finală a fiecărui bloc a fost verificată integral prin SHA256 față de referința inițială și prin 2.048 de valori CPU FP64; toate verificările au trecut. Rezultatele intermediare dintre aceste verificări nu au fost inspectate individual.

## Temperaturi și limitări

Maximul a fost **86°C în blocurile validării +150** și **87°C pe întreaga rundă**, acesta din urmă în controlul final la offset 0 MHz. Condițiile termice au evoluat pe durata testului; comparația nu demonstrează că offsetul +150 a cauzat toate diferențele termice.

În cele 2.848 de eșantioane active din ferestrele măsurate ale validării +150:

- SW Power Cap: **99,75%**.
- HW Thermal Slowdown și HW Slowdown: **0,07%**, două eșantioane pentru fiecare indicator, suprapuse.
- SW Thermal Slowdown și HW Power Brake: **0%**.

În controlul final la 0 MHz, SW Thermal Slowdown a apărut în 9,15% dintre eșantioanele active. Limitarea dominantă în validarea +150 rămâne puterea; limitarea termică hardware rară este o observație reală, nu o eroare numerică sau un eveniment WHEA. Procentele reprezintă eșantioane și nu atribuirea exactă a timpului CUDA. Nu s-a folosit prag artificial de oprire la temperatură.

Nu au fost înregistrate evenimente noi Display/nvlddmkm/WHEA sau de suspendare în intervalul verificat. Pornirea Windows a rămas aceeași, iar starea Secure Boot din registry a rămas 1. Controlul final la 0 MHz corespunde randamentului Tensor Core deblocat pe frecvență: 0,997× FP16 / 0,995× BF16 față de referința deblocată. Nu s-au citit direct selectorii GPU în Windows.

## Restaurare și repaus

Offseturile inițiale GPU și VRAM au fost verificate după restaurare de procesul principal, watchdog și o citire independentă. Intervenția watchdog-ului la blocare nu a fost provocată. Aplicația nu a modificat tensiuni fixe, limita de putere, VRAM, BIOS/VBIOS, chei Secure Boot sau configurația de boot.

Înaintea noii runde exista deja starea P0 la aproximativ 27 W, cu 0% utilizare. După restaurare, snapshotul final a arătat **P8, 210/405 MHz, aproximativ 12,23 W, 0% utilizare și 0 MiB alocați**. Cauza variației stării de repaus nu este stabilită și nu atribuim revenirea la P8 offsetului +150.

Tabelul standard `nvidia-smi` nu a enumerat procese nici în timpul acestui benchmark cunoscut, deși raporta 100% utilizare și 1.151 MiB. Prin urmare, lipsa proceselor din lista NVIDIA nu demonstrează singură absența clienților GPU în acest mediu.

## Evaluare practică

**+150 are un avantaj mic în GEMM-ul testat, aproximativ 1% debit suplimentar față de +120 în etapa comparativă.** Este un candidat de benchmark validat în această rundă, nu un profil universal certificat. Pentru aplicare automată zilnică, avantajul modest trebuie cântărit împreună cu deriva debitului, cele două eșantioane HW Thermal Slowdown și comportamentul de repaus variabil. Niciun profil suplimentar nu a fost instalat.

Date: `comparison-120-150.json`, `adaptive-summary.json`, `adaptive-review.json`, `phase-limiters.json`, `post-control-unlock.json`, `idle-before.csv`, `idle-after.csv`, `energy-blocks.jsonl`, `energy-telemetry.jsonl`, `offset-events.jsonl`. Codul executat este arhivat în `source/`.
