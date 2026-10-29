# Rezultate publicate

Acest director conține **copii anonimizate** ale rapoartelor și un set selectat de măsurători din laboratorul original. Valorile numerice de performanță, temperatură și putere, timpii și hashurile matricelor sunt păstrate. Căile personale, GUID-urile dispozitivelor/partițiilor și alte identificatoare locale sunt înlocuite sau eliminate.

| Experiment | Raport | Date publicate |
|---|---|---|
| Referință stock, 25 octombrie 2026 | [JSON](baseline-2026-10-25.json) | Configurație, rezultate, verificări numerice și telemetrie |
| FP16/BF16, 20 minute | [Raport](long-current-state-20261026-115633/REPORT.md) | before/after, review, blocuri și telemetrie |
| SS0+SS1 / TF32 fizic și 5 minute | [Raport](automatic-tf32-physical-20261026-193847/REPORT.md) | Review, logul tranzacției, blocuri și telemetrie TF32 |
| GEMM PyTorch, două rulări, 29 octombrie | [Raport](upstream-gemm-20261029-104056/REPORT.md) | Summary, review, telemetrie și offseturi |
| Fine-tuning CIFAR-100 | [Raport](training-cifar100-20261026-205139/REPORT.md) | Summary, review și rezultate pe precizie |

Celelalte rapoarte Markdown păstrează istoricul testelor, inclusiv încercări oprite, avertismente și experimente de offset. Unele fișiere citate în rapoarte **nu sunt incluse**: dumpuri UEFI, ROM-uri, executabile, inventare complete de boot/discuri, checkpointuri, dataseturi și planuri/autorizări ale instalării originale. Copiile `source/` ale rulărilor originale sunt de asemenea omise; sursele proiectului sunt în directoarele de la rădăcină.

Anonimizarea schimbă octeții fișierelor. Hashurile istorice citate în rapoarte descriu originalele locale, nu copiile publice, și nu oferă verificare completă a arhivei originale. `PUBLIC-MANIFEST.json` enumeră hashurile SHA-256 ale copiilor publicate. Rapoartele de trust descriu verificări efectuate local; exporturile brute necesare repetării integrale a auditului nu sunt distribuite.

Aceste fișiere nu sunt profiluri de instalare, aprobări sau dovezi pentru un alt calculator. Pentru măsurători proprii, folosește nume noi sub `results/` și propria referință stock. Rezultatele noi sunt ignorate implicit de Git și trebuie revizuite înaintea unei eventuale publicări.
