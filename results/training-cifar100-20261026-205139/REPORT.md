> Copie publică: identificatorii și căile locale au fost anonimizate. Unele exporturi și fișiere binare citate sunt păstrate doar în laborator. Vezi [politica datelor](../README.md).

# Antrenare reală: ResNet50 pe CIFAR-100 local

**Execuție și verificări: PASS.** Sănătate hardware: fără evenimente noi.

A fost folosit checkpointul existent `best_resnet50_cifar100_88_09.pth` și setul CIFAR-100 din proiectul „AI Summer School”, cu PyTorch și CUDA deja instalate. Fiecare precizie pornește independent din același checkpoint și parcurge o epocă întreagă: **50.000 de imagini, 782 de pași la batch 64**, apoi evaluare pe **10.000 de imagini de test**.

Checkpoint inițial: **87.98% top-1**, loss 0.60643, evaluat în FP32 strict. Model: 23,705,252 parametri. PyTorch 2.8.0+cu126, torchvision 0.23.0+cu126, CUDA 12.6, cuDNN 91002.

| Precizie train | Timp epocă, s | Imagini/s | Pas CUDA median, ms | VRAM alocată max., MiB | Loss train | Top-1 test |
|---|---:|---:|---:|---:|---:|---:|
| TF32 | 442.47 | 113.00 | 538.39 | 2968 | 0.38399 | 87.85% |
| BF16 | 65.71 | 760.87 | 52.58 | 1044 | 0.38485 | 87.81% |
| FP16 | 381.98 | 130.90 | 457.10 | 1044 | 0.38361 | 87.85% |

Cea mai rapidă variantă măsurată: **BF16**, 6.73× debitul TF32 în acest flux.

Timpul epocii include așteptarea DataLoader, augmentările, transferurile, forward/backward, gradient clipping și optimizerul. Exclude încălzirea, validarea și salvarea checkpointului. „Pas CUDA” este timpul pe stream între evenimente și poate include goluri între lansările de kernel; nu este suma exclusivă a timpului în kernel. VRAM este vârful alocărilor PyTorch, nu întreaga memorie ocupată a GPU-ului.

## Parametri și verificări

Rețea ResNet50 cu intrare 3×3, maxpool eliminat și cap Dropout(0,2) + Linear(2048,100), reconstruite fără descărcarea unor greutăți noi. Augmentări din proiect: RandomHorizontalFlip, RandomCrop reflectat, TrivialAugmentWide și normalizare ImageNet. SGD: lr 0,0001, momentum 0,9, weight decay 0,0001; normă maximă gradient 1. Batch 64, doi workers, seed 3060 și aceeași ordine salvată a imaginilor pentru toate variantele.

TF32 permite calcule TF32 în cuBLAS/cuDNN, cu greutăți și gradienți FP32. BF16 și FP16 folosesc autocast; FP16 are GradScaler. Toate validările folosesc FP32 strict. Verificările acoperă loss și normele gradienților finite la fiecare pas, parametri finiți, modificarea efectivă a greutăților și hashurile checkpointurilor salvate. Preciziile au traiectorii numerice diferite; nu se cere identitate bit cu bit între antrenări.

## Telemetrie și limite

Temperatură maximă pe întreaga rulare: **87°C**. Fără prag artificial de temperatură și fără modificarea offsetului GPU, tensiunii, limitei de putere sau a firmware-ului.

- TF32: așteptare date 1.7% din timpul epocii; utilizare GPU mediană 99%; 812 eșantioane cu utilizare ≥90%. Limitări în acele eșantioane: {"power": 76.60098522167488, "sw_thermal": 24.63054187192118, "hw_thermal": 1.2315270935960592, "hw_power_brake": 0.0}.
- BF16: așteptare date 11.6% din timpul epocii; utilizare GPU mediană 92%; 80 eșantioane cu utilizare ≥90%. Limitări în acele eșantioane: {"power": 100.0, "sw_thermal": 0.0, "hw_thermal": 0.0, "hw_power_brake": 0.0}.
- FP16: așteptare date 1.9% din timpul epocii; utilizare GPU mediană 99%; 689 eșantioane cu utilizare ≥90%. Limitări în acele eșantioane: {"power": 55.87808417997097, "sw_thermal": 45.86357039187228, "hw_thermal": 1.3062409288824384, "hw_power_brake": 0.0}.

Procentele sunt observații de telemetrie, nu o atribuire exactă a timpului CUDA. Diferențele dintre precizii includ alegerea kernelurilor, backendurile și overheadul acestui flux; nu le atribuim integral deblocării hardware. Toate variantele au fost rulate cu unlock activ și offset zero. **Nu există în acest test o măsurare de antrenare cu GPU blocat sau la +150 MHz.**

## Evenimente și fișiere păstrate

Nu au fost înregistrate evenimente noi Display/nvlddmkm/WHEA sau de suspendare în fereastra verificată.

Checkpointul original și fișierele datasetului au fost reverificate prin SHA256. Nu s-au instalat pachete și nu s-au descărcat modele/date. Checkpointurile noi sunt `finetuned-tf32.pth`, `finetuned-bf16.pth` și `finetuned-fp16.pth`, în acest director.

Rezultatul demonstrează o epocă de fine-tuning pe acest model și dataset, nu convergența unei antrenări noi sau stabilitatea în toate aplicațiile. Un singur parcurs per precizie nu reprezintă o comparație statistică de acuratețe.

Date: `training-summary.json`, `training-review.json`, `*-steps.jsonl`, `*-result.json`, `telemetry.jsonl`, `health-final.json`, `source/` și `training-order.npy`.

Implementarea AMP urmează [exemplele PyTorch 2.8](https://github.com/pytorch/pytorch/blob/v2.8.0/docs/source/notes/amp_examples.rst), iar opțiunile TF32 urmează [notele CUDA pentru aceeași versiune](https://github.com/pytorch/pytorch/blob/v2.8.0/docs/source/notes/cuda.rst).
