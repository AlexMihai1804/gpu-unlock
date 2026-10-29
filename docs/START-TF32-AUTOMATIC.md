> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Pornire automată FP16/BF16/TF32 — verificată fizic

**Înrolarea MOK și prima pornire SS1=8 sunt încheiate. Nu repeta înrolarea.** RUN0000 a confirmat SS0=88888888 / SS1=8, un FLR, curățare completă și pornirea Windows prin Boot0006 cu Secure Boot activ.

TF32: **13,537 → 23,467 TFLOPS (+73,35%)** față de controlul recent SS0-only; **+69,25% față de stock**. FP16: 42,039 TFLOPS; BF16: 45,076. Ieșirile complete sunt identice cu stock în fiecare mod.

Testul TF32 de 5 minute a trecut: **22,551 TFLOPS mediană**, 5.900 GEMM și 59 rezultate finale de bloc verificate, maximum **85°C**. Puterea a limitat GPU-ul în 99,62% dintre eșantioanele active; fără limitare termică raportată sau evenimente noi în sarcină. Ultimul sfert: −2,89% față de primul.

[Raport și date complete](../results/automatic-tf32-physical-20261026-193847/REPORT.md).

## Utilizare

Pornirea implicită este configurată **Boot0006 → Boot0000 → Boot0001**:

1. **M6501 GPU FP16 BF16 TF32**: SS0+SS1 automat, după 5 secunde.
2. **M6501 GPU automatic**: vechea variantă FP16/BF16, păstrată.
3. **Windows Boot Manager**: loaderul Microsoft original.

Nu ai nevoie de USB, T sau U. **Esc** în numărătoarea de 5 secunde sare peste schimbările GPU și pornește Windows.

La prima colectare după înrolare ordinea devenise 1,0,6; cauza nu este demonstrată. A fost readusă la 6,0,1 și verificată prin readback. Persistența la următoarele restarturi și după sleep/D3cold nu este încă certificată. Nu este necesară altă repornire acum.

## Verificare și revenire

Colectarea administrativă, numai prin citire:

```powershell
.\scripts\Collect-InternalAutomatic.ps1 -Profile TF32 -OutputDirectory "$PWD\results\tf32-post-BOOT-NEW"
```

Pentru a prefera vechea deblocare automată, păstrând fișierele, intrările și MOK:

```powershell
.\scripts\Set-GpuBootPriority.ps1 -Mode Previous
```

Pentru noua variantă prima:

```powershell
.\scripts\Set-GpuBootPriority.ps1 -Mode TF32
```

Comenzile de prioritate cer UAC și verifică identitatea celor trei intrări înainte de a modifica doar ordinea. Nu restaurează intrările USB dispărute și nu schimbă cheile, fișierele sau GPU-ul în sesiunea Windows curentă.

Dacă o tranzacție viitoare se oprește după ce a început sau laptopul se blochează, oprește-l complet înaintea altei încercări. Meniul ASUS cu Esc permite alegerea vechii intrări ori a Windows Boot Manager.

## Identitate instalată

- Imagine: `build/automatic-tf32-20261026-v1/M6501-AUTOMATIC-TF32.EFI`.
- SHA256 fișier: `f250951395b639cb6b5724d372423fe2d5763cddd0cc0067d774e9a2e26af255`.
- Hash PE/Authenticode MOK deja înrolat: `8420bdf786608237d3a9469f87b51f7734b99e9e234f89389d970f4dcf787e60`.
- Director intern: `EFI/M6501TF32`; partiția dedicată existentă M6501GPU.
- Instalare: `results/automatic-tf32-install-20261026-192644/`.
- Verificare fizică: `results/automatic-tf32-physical-20261026-193847/`.

Nu s-a făcut flash BIOS/VBIOS, redimensionare sau înlocuirea Windows Boot Manager. PK/KEK/db/dbx și intrările originale au trecut comparația cu exportul anterior.
