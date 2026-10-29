> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# TF32 pe M6501RM: diagnostic încheiat, candidat separat pregătit

**Rezultat ulterior: TF32 a fost accelerat și verificat fizic.** SS1=8 a trecut primul boot cu Secure Boot și MOK, benchmarkul de 23,467 TFLOPS și validarea de 5 minute la 22,551 TFLOPS mediană. [Raportul fizic](../results/automatic-tf32-physical-20261026-193847/REPORT.md) și [starea curentă](START-TF32-AUTOMATIC.md). Analiza de mai jos păstrează etapele de cercetare anterioare.

**Actualizare ulterioară:** utilizatorul a cerut „modifica ala sa pornim si cu tf32”. Varianta automată separată a fost construită, verificată și instalată. Hashul ei MOK diferă de cel manual de mai jos; înrolarea și primul boot SS1=8 sunt încă în așteptare. [Instrucțiunile curente](START-TF32-AUTOMATIC.md). Restul paginii documentează candidatul manual anterior.

Stare la 26 octombrie 2026: **nu există încă un câștig TF32 validat pe acest laptop**. Diagnosticul Windows a trecut. Candidatul SS0+SS1 a fost construit și verificat local, dar nu a fost instalat, înrolat în MOK sau executat pe GPU. Deblocarea automată FP16/BF16 existentă nu a fost înlocuită.

## Ce am măsurat acum

`results/tf32-diagnostic-20261026-185622/diagnostic.json` conține șapte cazuri cu cuBLAS fixat, matrice 8192×8192, acumulare/ieșire FP32, o secundă de încălzire și mediane de 3×5 multiplicări. CUPTI 12.9.79 a observat numele kernelurilor prin callbackuri de lansare ale procesului propriu. Nu au fost activate contoare de performanță, servicii, injecție în alte procese sau scrieri de configurație GPU.

| Caz TF32 | Math mode | TFLOPS |
|---|---:|---:|
| Configurația benchmarkului original | 16 | 13,451 |
| DEFAULT_MATH | 0 | 13,482 |
| TF32_TENSOR_OP_MATH cu reducere FP32 | 19 | 13,483 |
| Repetarea configurației originale | 16 | 13,417 |

Toate au lansat același kernel: `_ZN7cutlass7Kernel2I52cutlass_80_tensorop_s1688gemm_128x256_16x3_nn_align4EEvNT_6ParamsE`. Compute type cerut: `CUBLAS_COMPUTE_32F_FAST_TF32` (77). Kernelul FP32 de control este `cutlass_80_simt_sgemm_256x128_8x4_nn_align1`, diferit de cel TF32. Aceste observații susțin utilizarea traseului Tensor Core TF32; nu reprezintă contoare hardware ori dezasamblarea SASS.

Modificarea math mode nu aduce accelerarea lipsă. Toate ieșirile TF32 au același SHA256, inclusiv față de stock; eroarea relativă L2 pe cele 2.048 de valori de control este 0,00028165, sub toleranța 0,003. Au trecut și controalele FP16/BF16/FP32. Maximum observat: 67°C. Jurnalul de evenimente verificat după diagnostic este gol. Offseturile GPU/VRAM sunt identice înainte/după, GPU la offset 0; Secure Boot în registry este 1.

Timpii acestei rulări sunt instrumentați. Nu îi amestecăm cu măsurătorile neprofilate pentru a calcula un câștig stock/unlock. Telemetria pe fază include inițializare și încălzire; normalizarea ei nu este sincronizată cu ferestrele CUDA. În special, valoarea FP16/GHz calculată din prima fază este afectată de pornirea GPU-ului și nu este folosită pentru clasificarea deblocării.

## De ce investigăm SS1

Varianta fizic validată aici scrie SS0 `0x88888888`, păstrând SS1 `0x3`. Upstream scrie și SS1 `0x8`. Documentația upstream atribuie SS1 câmpului IMLA4; aceasta nu stabilește singură o corespondență universală SS1–TF32.

- [RTX 3060 Laptop pe Linux, raport #53](https://github.com/Zagitta/gpu-unlock/issues/53): TF32 11,4 → 17,6 TFLOPS, cu implementarea care scrie ambii selectori. Alt laptop, VBIOS și driver.
- [RTX 3060 Laptop pe Windows, SS0-only, raport #58](https://github.com/Zagitta/gpu-unlock/issues/58): TF32 aproximativ neschimbat, FP16/BF16 accelerate.
- [GA106 desktop pe Windows, ambii selectori](https://github.com/impacifist/Windows-GPU-UNLOCK/blob/5c98f11eaafdcb7a2a06fb14fcdcde7297eb409e/evidence/h610m-3060-usb/README.md): TF32 13,50 → 24,02 TFLOPS. Este un raport al contributorului pentru altă placă, nu validare pe M6501RM.
- [Definițiile NVIDIA pentru issue-rate modifiers](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/ca2d03e6fafd4d4b56b383497d931c25b283bfcf/src/common/sdk/nvidia/inc/ctrl/ctrl2080/ctrl2080gr.h) disting câmpurile FMLA/IMLA. Nu am apelat comenzi RM private în Windows.
- [Documentația cuBLAS](https://docs.nvidia.com/cuda/cublas/index.html#cublascomputetype-t) descrie compute type TF32, iar [CUPTI](https://docs.nvidia.com/cupti/12.8/api/structCUpti__CallbackData.html) documentează numele de kernel din callback.

**Ipoteză de test, nu cauză demonstrată:** pe această placă, SS0-only lasă o limitare relevantă pentru TF32; SS1=8 ar putea permite debitul suplimentar. Diferențele de driver și inițializare rămân posibile. Numai o comparație pe aceeași placă poate confirma efectul și compatibilitatea driverului 580.97.

## Candidatul de revizuit

- Imagine: `build/tf32-ss1-20261026-v4/M6501-TF32-SS1-CANDIDATE.EFI`.
- SHA256 fișier: `517c38d22a8d4c31ac0f9c168efbb2d984128d8e3ac08082e43177edbdcaf25c`.
- **Hash PE/Authenticode pentru MOK:** `4c98895062ce71acf4f117e7a2b63176a8e528d545a72e39f97d446866803198`.
- Pachet intern local: `build/release-tf32-20261026-v4/INTERNAL-CANDIDATE/`.
- Variantă USB locală: `build/release-tf32-20261026-v4/USB-CANDIDATE/`.
- Readiness: `results/tf32-investigation-20261026/candidate-ready.json`, zece verificări trecute.

Nucleul SS0+SS1 este identic la nivel de octeți cu `craftingmod/rtx30-unlock` commit `5c076dc4ee7fa369639669fa591ac74d8f6dfcd8`; activele GPU rămân fixate. Este păstrat exact profilul plăcii: SMBIOS/BIOS, PCI/subsystem/revizie, chip, 6 GB, hash ROM, fuse, layout, GOP AMD și Windows ESP verificat prin GUID.

Experimentul acceptă numai SS1 inițial 3, cere **T** fizic, scrie SS0 `0x88888888` și SS1 `8`, apoi cere readback înainte/după un singur FLR, curățare DMA și handoff către Windows Boot Manager existent. O eroare după începerea tranzacției oprește continuarea; nu există retry automat în același ciclu. Esc sau lipsa confirmării nu aplică tranzacția.

Activele/logurile sunt în `EFI/M6501TF32/RTX-UNLOCK`, separat de `EFI/M6501GPU`. Pachetul intern poate folosi ESP-ul dedicat existent, fără redimensionare sau USB permanent. Încă nu există o nouă intrare de boot instalată. Intrarea de test și mecanismul de selectare o singură dată trebuie verificate la instalarea autorizată; nu se înlocuiește intrarea automată actuală.

Candidatul manual refuză combinarea opțiunii `--ss1-full-experiment` cu `--automatic`. Pentru cererea ulterioară a utilizatorului există opțiunea distinctă `--automatic-ss1-experiment`, cu build, instalare și hash MOK separate. Installerul automat vechi nu se folosește pentru aceste pachete.

## Verificări efectuate

- 22 scenarii cu nucleul real, ROM/configurație PCI salvate și servicii UEFI simulate, inclusiv refuzul scrierii SS1, readback greșit și pierderea selectorului după FLR.
- 14 cazuri preflight pe ROM-ul salvat: inclusiv refuzul SS1 diferit de 3, chip/ROM/fuse/VRAM/WPR/MSI necorespunzătoare; accesul de scriere este interzis în aceste teste.
- Regresia traseului SS0: 43 teste Python, nouă grupuri native, inclusiv 20 scenarii de tranzacție simulate. Nucleul SS0 rezultat este identic cu cel automat deja validat.
- Imaginea experimentală reală a fost acceptată de shim cu MOK **virtual**, în OVMF cu Secure Boot, pe NVMe emulat. Directorul privat a funcționat. Lipsa GPU-ului a produs refuz înainte de orice scriere MMIO.
- Fișierele pachetului au fost verificate prin hash. PE AMD64 EFI, NX, SBAT, relocări și lipsa importurilor Windows au trecut inspecția.

VM-ul nu emulează GPU-ul sau firmware-ul ASUS. Oprirea lui la timeout de 25 s este intenționată după refuzul aplicației. Nu validează SS1, câștigul TF32 sau driverul real. Nicio verificare locală nu autorizează sau execută singură testul fizic.

## Reproducere locală

Se aleg directoare noi, deoarece un build sau staging existent nu se suprascrie:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/build.py --board config/board.reviewed.json --output build/tf32-ss1-NEW --ss1-full-experiment
.\.venv\Scripts\python.exe -X utf8 tools/test_capture_transaction.py --evidence results/physical-capture-20261025-201848 --build-root build/tf32-ss1-NEW --output-name saved-board-full-ss1 --ss1-full-experiment
.\.venv-vm\Scripts\python.exe -X utf8 tools/test_tf32_vm.py --image build/tf32-ss1-NEW/M6501-TF32-SS1-CANDIDATE.EFI
.\.venv\Scripts\python.exe -X utf8 tools/stage_tf32_experiment.py --build-root build/tf32-ss1-NEW --output build/release-tf32-NEW/INTERNAL-CANDIDATE
```

Un rebuild poate schimba hashul PE, inclusiv din cauza căilor din diagnostice; nu se presupune că hashul MOK de mai sus îl autorizează. Reproducerile sunt locale și nu schimbă firmware-ul sau bootul.

Pentru diagnosticul Windows, CUPTI este extras local din `nvidia_cuda_cupti_cu12-12.9.79-py3-none-win_amd64.whl`, SHA256 `1848a9380067560d5bee10ed240eecc22991713e672c0515f9c3d9396adf93c8`. Nu a fost instalat în sistem sau în mediul Python. Proveniența și URL-ul exact sunt în `tools/downloads/cupti-12.9.79/provenance.json`. Apoi:

```powershell
.\.venv\Scripts\python.exe -X utf8 bench/tf32_diagnostic.py --output-directory results/tf32-diagnostic-NEW
```

## Următorul test fizic, numai după acord

1. Se verifică din nou identitatea/free space ale ESP-ului dedicat și fișierele automate existente. Se copiază separat `EFI/M6501TF32`; fără flash, redimensionare, înlocuirea Windows Boot Manager sau modificarea cheilor PK/KEK/db/dbx.
2. Se autorizează numai hashul PE al candidatului prin MokManager, apoi se selectează manual experimentul. **Înrolarea MOK este o schimbare persistentă de trust shim**, separată de cheile platformei; candidatul nou nu este acoperit de hashul vechi.
3. Se păstrează Performance, AC și offset 0; o singură tranzacție GPU autorizată, confirmată prin T. Dacă apare STOP/black screen, se oprește complet; nu se repetă încercarea în același ciclu.
4. După Windows: logul trebuie să arate SS0=88888888 / SS1=8 și curățare completă. Se verifică Secure Boot, driverul/evenimentele, apoi benchmarkul original cu patru moduri, aceleași matrice/biblioteci și verificări numerice. Câștigul se compară cu un control SS0-only proaspăt, la condiții apropiate, și se repetă măsurarea în același boot.
5. Numai dacă TF32 crește repetat și toate controalele rămân corecte se continuă validarea de durată. Aplicarea automată zilnică este o etapă ulterioară, după demonstrarea efectului și a revenirii la profilul actual.

Nu este programată o repornire și nu a fost efectuată înrolarea sau tranzacția SS1 pe laptop.
