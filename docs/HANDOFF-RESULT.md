> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# HANDOFF fizic — 25 octombrie 2026

**Rezultat funcțional: trecut.** Windows a pornit prin lanțul UEFI ASUS → shim → HANDOFF → Windows Boot Manager existent, cu Secure Boot activ. Nu a fost aplicată deblocarea GPU. Controlul ulterior, cu Windows pornit direct fără USB, a reprodus avertismentul PCIe corectat al portului Realtek; avertismentul nu este specific rutei HANDOFF. Ulterior CAPTURE a fost autorizat și copiat pe stick; captura este încă neexecutată.

Logul `results/physical-handoff-20261025-192433/RUN04/UNLOCK.TXT` conține:

```text
SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero
SMBIOS M6501RM_product=1 BIOS_313=1
TARGET exact_matches=1
GOP owner=16811002 independent_AMD=1 framebuffer=0x7e70000000 bytes=18662400
WINDOWS_PRELOAD status=0 unique_GUID_match=1
HANDOFF-ONLY status=0 no_GPU_writes=1 no_firmware_load=1
```

Utilizatorul a confirmat revenirea în Windows, iar benchmarkul de control a rulat ulterior pe RTX 3060 Laptop. Astfel, rezultatul nu se bazează numai pe mesajul de preîncărcare din UEFI.

Exportul administrativ numai pentru citire este în `results/uefi-post-handoff-20261025-192433/`. SecureBoot=1, SetupMode=0. MokListRT include atât hashul PROBE, cât și hashul HANDOFF exact `578950703436fdda4130666bf45f168e419d5d9932babdc81ac67281bbe24c5f`. Fișierul HANDOFF de pe USB a fost recitit și coincide cu buildul verificat, SHA-256 `c646f027c42795505b6f3b618e3f5586920054fe2c94b57ac288f1aab238c83b`.

PK/KEK/db/dbx sunt identice octet cu octet cu exportul inițial. Blocul Windows Boot Manager este identic și rămâne primul în ordine. Driverul este 580.97, VBIOS 94.06.38.00.38. Alimentare AC, baterie raportată 100% înaintea benchmarkului.

Benchmark de control, fără unlock

| Mod | Referință TFLOPS | După HANDOFF TFLOPS | Diferență | Ieșire integral identică |
|---|---:|---:|---:|---|
| FP16 | 27,204 | 27,119 | −0,31% | Da |
| BF16 | 27,694 | 27,729 | +0,13% | Da |
| TF32 | 13,865 | 13,856 | −0,07% | Da |
| FP32 | 9,343 | 9,336 | −0,08% | Da |

Aceleași biblioteci, parametri, intrări și identitate GPU au fost verificate de comparator. Toate ieșirile sunt finite și toate verificările numerice au trecut. Fișier brut: `results/handoff-control-2026-10-25.json`. Diferența maximă de performanță este 0,315%; acest control nu demonstrează stabilitate pe termen lung.

Analiză reproductibilă, numai pe fișiere locale:

```powershell
.\.venv\Scripts\python.exe tools/review_handoff.py --evidence results/physical-handoff-20261025-192433 --post results/uefi-post-handoff-20261025-192433 --control results/handoff-control-2026-10-25.json
```

Raportul rezultat: `results/physical-handoff-20261025-192433/handoff-review.json`.

Avertisment PCIe și control necesar

În bootul HANDOFF curent există un WHEA-Logger 17 corectat pe portul `0000:00:02.1`, AMD `1022:14ba`. Relația PnP identifică dispozitivul conectat drept **Realtek Gaming 2.5GbE Family Controller**, cu stare OK; Ethernet este deconectat și Wi-Fi este activ. Nu este portul NVIDIA `0000:00:01.1` / `1022:14b8`. Nu au fost găsite evenimente Display/nvlddmkm de nivel 1–3 în bootul curent.

Evenimentul raportează `UncorrectableErrorStatus=0` și `CorrectableErrorStatus=0xc0`. Conform [definiției Microsoft a registrului](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-_pci_express_correctable_error_status), 0xc0 corespunde biților BadTLP și BadDLLP. Această decodare nu stabilește cauza.

Din 132 de evenimente WHEA 17 citite pentru ultimele 14 zile, cinci privesc portul 14ba și apar după pornirile Windows recente, la aproximativ 22–26 s de la boot. Primul este la 16:49:28 UTC, după primul test USB; nu a fost găsit un eveniment pentru același port înaintea acelui test în intervalul căutat. Există multe avertismente mai vechi pentru alt port, 14b8, dar acestea nu dovedesc că avertismentul Realtek era preexistent. Nu atribuim și nu excludem o legătură cu ruta USB în lipsa controlului comparabil.

Date: `gpu-events.json`, `whea-current-fields.json`, `whea-history.json`, `whea-port-history-summary.json` și `recent-windows-boots.json`, în directorul dovezilor HANDOFF. Următorul control este o oprire completă cu `shutdown /s /t 0` lansată manual după salvarea lucrului, scoaterea USB-ului după oprire și pornirea Windows direct, apoi așteptarea unui minut la desktop și recitirea jurnalului. [Microsoft documentează oprirea completă fără /hybrid](https://learn.microsoft.com/en-us/troubleshoot/windows-client/setup-upgrade-and-drivers/fast-startup-causes-system-hibernation-shutdown-fail); setarea Fast Startup nu este modificată. Nu se schimbă drivere, ASPM, chei, setări BIOS sau alte opțiuni Windows pentru a ascunde avertismentul.

Pregătire pentru CAPTURE

Snapshotul PCI de 256 bytes din log a fost reanalizat offline cu funcția `GuCheckConfig` din nucleul fixat, folosind identitatea acestui laptop. Ca în adaptorul CAPTURE, bitul MEMORY a fost adăugat **numai unei copii în RAM a snapshotului**, fără acces PCI real. Verificarea a trecut: Command original 0, PM la 0x60, MSI la 0x68, PCIe v2 la 0x78, stare D0 și condițiile capabilităților acceptate de nucleu. Raport: `results/physical-handoff-20261025-192433/pci-offline/report.json`.

Aceasta nu demonstrează încă proprietatea exclusivă PCI, descriptorul BAR0, ferestrele punților, activarea/restaurarea MEMORY sau citirea PROM. Acestea sunt verificări ale etapei fizice CAPTURE. RomImage raportată de UEFI are 148.992 bytes; nu reprezintă captura PROM completă de 1 MiB necesară analizei FWSEC.

Controlul Windows direct a fost efectuat: boot nou la 17:42:36 UTC, fără USB, reconectat după desktop conform confirmării utilizatorului. Nu a apărut un log HANDOFF nou pe USB. A fost înregistrat din nou un singur WHEA 17 la același port 14ba, cu `CorrectableErrorStatus=0x40` și `UncorrectableErrorStatus=0`; niciun eveniment Display/nvlddmkm de nivel 1–3. Secure Boot este activ. Comparația este în `results/normal-boot-control-20261025-194422/comparison.json`.

Acest rezultat arată că avertismentul poate apărea și fără pornirea shim/HANDOFF în acel boot. Nu demonstrează cauza, absența oricărui efect anterior sau sănătatea tuturor dispozitivelor. Nu au fost modificate drivere sau setări pentru a-l elimina.

Următorul pas autorizat este [CAPTURE](CAPTURE-PLAN.md): înrolarea hashului său distinct și, după tasta P, activarea temporară MEMORY dacă este necesară, citirea ROM-ului/registrelor și restaurarea atributelor originale. Fără execuție firmware GPU, DMA, FLR sau unlock. CAPTURE este acum pe USB, dar nu a fost încă înrolat sau executat; copia HANDOFF și logurile sunt păstrate local.
