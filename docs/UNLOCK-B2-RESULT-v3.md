> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# A doua pornire experimentală v3: B2 a trecut

**Actualizare: controlul normal A3 a trecut. Nu repeta pașii A3 de mai jos.** Vezi [rezultatul A3](NORMAL-RETURN-A3-RESULT-v3.md) și [următoarea etapă B3, deja autorizată](START-B3-v3-AUTHORIZED.md).

RUN07 a executat candidatul v3 neschimbat, autorizat prin acordul „aprob” pentru B2 → A3 → B3 → A4. Windows a pornit în același ciclu la `2026-10-25T19:50:59.5000000Z` (21:50:59, ora Bucureștiului). Nu a fost necesară o nouă înrolare MOK.

| Mod | Referință A1, TFLOPS | Primul unlock B1 | Al doilea unlock B2 | B2 față de A1 |
|---|---:|---:|---:|---:|
| FP16 → FP32 | 27,204 | 42,710 | 42,953 | +57,89% |
| BF16 → FP32 | 27,694 | 44,726 | 43,966 | +58,76% |
| TF32 → FP32 | 13,865 | 13,829 | 13,841 | −0,17% |
| FP32 | 9,343 | 9,347 | 9,303 | −0,43% |

Benchmarkul folosește aceleași matrice 8192×8192, biblioteci, driver, acumulare FP32, încălzire și eșantionare ca A1/B1/A2. Toate ieșirile sunt finite, verificările numerice CPU FP64 au trecut și hashurile întregilor ieșiri coincid cu A1 și A2. Raportul include și comparația cu A2, controlul normal imediat precedent. Niciun benchmark nu aplică unlock.

## Tranzacție și starea Windows

- Chipul, ROM-ul live, fuse și geometria de 6 GB au trecut aceleași verificări înaintea tranzacției.
- SS0 a devenit `0x88888888`; SS1 citit în acest boot era `0x3` și a fost păstrat fără scriere.
- FWSEC a fost observat rulând și apoi oprit, cu scratch zero și WPR2 în intervalul așteptat. Un singur FLR a reușit.
- La handoff: zero mapări DMA rămase, zero resurse reținute, GPU quiesced, acces PCI restaurat și Windows Boot Manager existent pornit.
- SecureBoot=1, SetupMode=0, validarea shim activă și hashul candidatului prezent în MOK. PK/KEK/db/dbx și intrarea Windows Boot Manager sunt identice cu exportul inițial; Windows Boot Manager rămâne primul.
- Nu există evenimente Display/nvlddmkm în acest boot până la colectarea după benchmark. Un WHEA 17 corectat apare pe portul AMD `00:02.1` al Realtek, cu UncorrectableErrorStatus zero, același tip observat și fără USB. Cauza lui rămâne neconfirmată.
- Telemetria activă eșantionată arată maximum 66°C la FP16 și 67°C la BF16. Eșantioanele includ încălzirea și nu stabilesc energia exactă per GEMM sau TGP-ul efectiv.

## Dovezi și reproducere a analizei

Director: `results/physical-unlock-B2-20261025-215254/`. Conține numai noua tentativă RUN07 și ROM-ul ca dovezi de încercare; cele șapte loguri istorice sunt inventariate separat și sunt identice cu arhiva B1. Toate cele 20 de fișiere ale pachetului USB au fost verificate înaintea măsurării.

- `unlock-review.json`: tranzacție, acord, controlul precedent, trust, benchmark și sănătatea driverului.
- `telemetry-comparison.json`: eșantioane active A1/A2/B2.
- `results/unlock-v3-B2-2026-10-25.json`: măsurările brute și hashurile numerice.
- `results/uefi-post-unlock-B2-20261025-215254/`: exportul administrativ prin citire.

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/review_unlock.py --stage B2 --evidence results/physical-unlock-B2-20261025-215254 --post results/uefi-post-unlock-B2-20261025-215254 --benchmark results/unlock-v3-B2-2026-10-25.json --paired-reference results/normal-return-A2-2026-10-25.json
```

Analizorul a fost adaptat pentru acordul separat cu două încercări, fără schimbarea codului sau executabilului UEFI. Cele 29 de teste Python, inclusiv respingerea unui control vechi/eșuat, a unui executabil diferit și a unei încercări în afara ordinii aprobate, au trecut. Raport: `results/repro-B2-review-unit-tests.log`.

## Următorul pas: controlul normal A3

1. Salvează lucrul. Win+R → `shutdown /s /t 0` → Enter.
2. După oprirea completă, scoate USB și pornește laptopul normal, fără Esc.
3. După desktop, reconectează USB și anunță revenirea. Nu reporni și nu intra în sleep până la verificarea logurilor și benchmarkului A3.

B3 rămâne autorizat în același acord, cu o singură încercare rămasă, dar urmează numai după A3 reușit. Două porniri experimentale reușite și controlul A2 sunt dovezi de repetabilitate parțială; A3/B3/A4, sleep/resume și stabilitatea de durată nu sunt validate încă. Nu s-au făcut flash BIOS/VBIOS sau înlocuiri ale cheilor platformei ori ale Windows Boot Manager.
