> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Controlul normal A3 a trecut

Utilizatorul a confirmat pornirea fără USB, după oprirea completă, și reconectarea la desktop. Windows a pornit la `2026-10-25T19:57:38.5000000Z` (21:57:38, București). Cele opt loguri RUN00–RUN07 sunt identice cu inventarul de după B2. Cele 20 de fișiere ale pachetului și ROM-ul sunt neschimbate. Nu a apărut o lansare suplimentară a aplicației UEFI.

| Mod | Referință A1, TFLOPS | Unlock B2 | Boot normal A3 |
|---|---:|---:|---:|
| FP16 → FP32 | 27,204 | 42,953 | 26,948 |
| BF16 → FP32 | 27,694 | 43,966 | 27,498 |
| TF32 → FP32 | 13,865 | 13,841 | 13,720 |
| FP32 | 9,343 | 9,303 | 9,275 |

Abaterea maximă A3 față de A1 este **1,0492%**. Același benchmark, driver și biblioteci au fost folosite. Toate ieșirile sunt finite; verificările numerice CPU FP64 au trecut, iar hashurile întregilor ieșiri coincid cu referința și B2. Aceasta arată revenirea performanței la nivelul normal; selectorii GPU nu au fost citiți direct în Windows.

SecureBoot=1, SetupMode=0. PK/KEK/db/dbx și intrarea Windows Boot Manager sunt identice cu exportul inițial; Windows Boot Manager rămâne primul. Variabilele runtime shim nu sunt expuse în această pornire normală, ceea ce nu dovedește ștergerea MOK persistent. Inventarul dispozitivelor de boot amovibile poate varia automat.

Nu există evenimente Display/nvlddmkm până la colectarea după benchmark. Este prezent avertismentul WHEA 17 corectat al portului Realtek `00:02.1`, fără eroare necorectabilă, observat și în controalele normale anterioare. Cauza lui rămâne neconfirmată.

## Dovezi

- `results/normal-return-A3-20261025-215939/normal-return-review.json`.
- `results/normal-return-A3-2026-10-25.json`: benchmark și telemetrie brute.
- `results/uefi-normal-return-A3-20261025-215939/`: export administrativ prin citire.
- `results/repro-A3-review-unit-tests.log`: 34 de teste Python trecute, inclusiv verificarea arhivei și respingerea modificării/dispariției logurilor sau a unei lansări suplimentare pe USB.

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/review_normal_return.py --stage A3 --evidence results/normal-return-A3-20261025-215939 --post results/uefi-normal-return-A3-20261025-215939 --benchmark results/normal-return-A3-2026-10-25.json --previous-unlock results/physical-unlock-B2-20261025-215254
```

Analizorul citește dovezile etapei precedente explicit și compară istoricul complet al stickului, chiar dacă arhiva tentativei conține numai noul RUN07. Codul și executabilul UEFI nu au fost schimbate.

Au trecut A1 → B1 → A2 → B2 → A3. B3 este deja autorizat, cu o singură încercare rămasă, urmat de controlul A4. Sleep/resume și stabilitatea de durată rămân nevalidate. Instrucțiunile următoarei etape sunt în [START-B3-v3-AUTHORIZED.md](START-B3-v3-AUTHORIZED.md).
