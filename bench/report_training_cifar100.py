"""Offline review of the local CIFAR-100 fine-tuning experiment."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def review(out):
    def read(name):
        return json.loads((out / name).read_text(encoding='utf-8-sig'))

    state = read('training-summary.json')
    runs = {run['mode']:run for run in state['runs']}
    original, final = [read(name) for name in ('inventory-before.json', 'inventory-after.json')]
    contexts = [read(name) for name in ('context-before.json', 'context-after.json')]
    mode_checks = {}
    for mode, run in runs.items():
        steps = [json.loads(line) for line in (out / f'{mode}-steps.jsonl').read_text().splitlines()]
        checkpoint = Path(run['checkpoint']).resolve()
        mode_checks[mode] = dict(
            full_train_and_test=run['examples']==50000 and run['validation']['examples']==10000,
            all_steps_recorded=len(steps)==run['steps']==math.ceil(50000/state['configuration']['batch_size']),
            examples_match=sum(row['examples'] for row in steps)==run['examples'],
            finite_loss_and_gradients=all(math.isfinite(row['loss']) and math.isfinite(row['gradient_norm']) for row in steps),
            finite_parameters_and_updates=run['all_parameters_finite'] and run['classifier_weight_change_l2']>0,
            no_fp16_scale_backoff=all(b['scaler_scale']>=a['scaler_scale'] for a,b in zip(steps,steps[1:])),
            checkpoint_hash_matches=checkpoint.is_relative_to(out) and digest(checkpoint)==run['checkpoint_sha256'])
    checks = dict(completed=state['completed'] and state['status']=='passed',
        all_three_modes=set(runs)=={'tf32','bf16','fp16'},
        full_dataset=state['train_examples_per_mode']==50000 and state['validation_examples']==10000,
        source_matches=digest(out/'source/train_existing_cifar100.py')==state['source_sha256'],
        training_order_matches=digest(out/'training-order.npy')==state['training_order_sha256'],
        original_checkpoint_unchanged=digest(Path(state['checkpoint']))==state['checkpoint_sha256'],
        original_dataset_unchanged=all(digest(Path(state['dataset'])/'cifar-100-python'/name)==value
                                       for name,value in state['dataset_hashes'].items()),
        all_mode_checks=bool(mode_checks) and all(all(checks.values()) for checks in mode_checks.values()),
        zero_graphics_and_memory_offsets=all(row['offset']==0 for row in final['graphics_offsets'].values()) and final['memory_offset']['offset']==0,
        offsets_unchanged=original['graphics_offsets']==final['graphics_offsets'] and original['memory_offset']==final['memory_offset'],
        same_boot_secure_boot=contexts[0]['windows_boot_utc']==contexts[1]['windows_boot_utc']
            and contexts[0]['secure_boot_registry']==contexts[1]['secure_boot_registry']==1,
        no_gpu_settings_changed=not state['gpu_configuration_changed'],
        launcher_completed=(out/'launcher-exit.txt').read_text().strip()=='0')
    telemetry = [json.loads(line) for line in (out/'telemetry.jsonl').read_text().splitlines()]
    limiters = {}
    for mode, run in runs.items():
        active = [row for row in telemetry if row['phase']==mode+'-train' and row['utilization_percent']>=90]
        training_samples = [row for row in telemetry if row['phase']==mode+'-train']
        limiters[mode] = dict(samples=len(training_samples), active_samples=len(active),
            median_utilization_percent=sorted(row['utilization_percent'] for row in training_samples)[len(training_samples)//2] if training_samples else None,
            limiter_sample_percent={name:100*sum(bool(row['clocks_event_reasons']&bit) for row in active)/len(active) if active else None
                for name,bit in dict(power=4,sw_thermal=32,hw_thermal=64,hw_power_brake=128).items()})
    events = read('health-final.json')['events']
    passed = all(checks.values())
    result = dict(measurement_passed=passed, checks=checks, mode_checks=mode_checks,
        hardware_health_clean=not events, hardware_events=events, limiter_telemetry=limiters,
        baseline_validation=state['baseline_validation'], runs=state['runs'],
        maximum_temperature_c=state['maximum_temperature_c'],
        scope=state['scope'], original_files_preserved=True if checks['original_checkpoint_unchanged'] and checks['original_dataset_unchanged'] else False)
    (out/'training-review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    lines = ['# Antrenare reală: ResNet50 pe CIFAR-100 local', '',
        f"**Execuție și verificări: {'PASS' if passed else 'INCOMPLETE'}.** Sănătate hardware: {'fără evenimente noi' if not events else 'CU AVERTISMENT; vezi evenimentele de mai jos'}.", '',
        'A fost folosit checkpointul existent `best_resnet50_cifar100_88_09.pth` și setul CIFAR-100 din proiectul „AI Summer School”, cu PyTorch și CUDA deja instalate. Fiecare precizie pornește independent din același checkpoint și parcurge o epocă întreagă: **50.000 de imagini, 782 de pași la batch 64**, apoi evaluare pe **10.000 de imagini de test**.', '',
        f"Checkpoint inițial: **{state['baseline_validation']['top1_percent']:.2f}% top-1**, loss {state['baseline_validation']['loss']:.5f}, evaluat în FP32 strict. Model: {state['parameters']:,} parametri. PyTorch {state['torch']}, torchvision {state['torchvision']}, CUDA {state['cuda_runtime']}, cuDNN {state['cudnn']}.", '',
        '| Precizie train | Timp epocă, s | Imagini/s | Pas CUDA median, ms | VRAM alocată max., MiB | Loss train | Top-1 test |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for mode in ('tf32','bf16','fp16'):
        row = runs[mode]
        lines.append(f"| {mode.upper()} | {row['wall_seconds']:.2f} | {row['images_per_second']:.2f} | {row['median_cuda_stream_step_ms']:.2f} | {row['peak_allocated_mib']:.0f} | {row['train_loss']:.5f} | {row['validation']['top1_percent']:.2f}% |")
    fastest=max(runs.values(),key=lambda row:row['images_per_second'])
    lines += ['', f"Cea mai rapidă variantă măsurată: **{fastest['mode'].upper()}**, {fastest['images_per_second']/runs['tf32']['images_per_second']:.2f}× debitul TF32 în acest flux.", '',
        'Timpul epocii include așteptarea DataLoader, augmentările, transferurile, forward/backward, gradient clipping și optimizerul. Exclude încălzirea, validarea și salvarea checkpointului. „Pas CUDA” este timpul pe stream între evenimente și poate include goluri între lansările de kernel; nu este suma exclusivă a timpului în kernel. VRAM este vârful alocărilor PyTorch, nu întreaga memorie ocupată a GPU-ului.', '',
        '## Parametri și verificări', '',
        'Rețea ResNet50 cu intrare 3×3, maxpool eliminat și cap Dropout(0,2) + Linear(2048,100), reconstruite fără descărcarea unor greutăți noi. Augmentări din proiect: RandomHorizontalFlip, RandomCrop reflectat, TrivialAugmentWide și normalizare ImageNet. SGD: lr 0,0001, momentum 0,9, weight decay 0,0001; normă maximă gradient 1. Batch 64, doi workers, seed 3060 și aceeași ordine salvată a imaginilor pentru toate variantele.', '',
        'TF32 permite calcule TF32 în cuBLAS/cuDNN, cu greutăți și gradienți FP32. BF16 și FP16 folosesc autocast; FP16 are GradScaler. Toate validările folosesc FP32 strict. Verificările acoperă loss și normele gradienților finite la fiecare pas, parametri finiți, modificarea efectivă a greutăților și hashurile checkpointurilor salvate. Preciziile au traiectorii numerice diferite; nu se cere identitate bit cu bit între antrenări.', '',
        '## Telemetrie și limite', '',
        f"Temperatură maximă pe întreaga rulare: **{state['maximum_temperature_c']}°C**. Fără prag artificial de temperatură și fără modificarea offsetului GPU, tensiunii, limitei de putere sau a firmware-ului.", '']
    for mode,row in runs.items():
        info=limiters[mode]
        lines.append(f"- {mode.upper()}: așteptare date {100*row['data_wait_seconds']/row['wall_seconds']:.1f}% din timpul epocii; utilizare GPU mediană {info['median_utilization_percent']}%; {info['active_samples']} eșantioane cu utilizare ≥90%. Limitări în acele eșantioane: {json.dumps(info['limiter_sample_percent'])}.")
    lines += ['', 'Procentele sunt observații de telemetrie, nu o atribuire exactă a timpului CUDA. Diferențele dintre precizii includ alegerea kernelurilor, backendurile și overheadul acestui flux; nu le atribuim integral deblocării hardware. Toate variantele au fost rulate cu unlock activ și offset zero. **Nu există în acest test o măsurare de antrenare cu GPU blocat sau la +150 MHz.**', '',
        '## Evenimente și fișiere păstrate', '']
    if events:
        for event in events:
            lines.append(f"- {event['utc']}: {event['provider']} {event['id']}; {json.dumps(event.get('fields',{}))}")
        lines += ['', 'Evenimentele corectate sunt raportate; nu sunt șterse din jurnal și nu sunt prezentate ca un verdict hardware complet curat.']
    else:
        lines.append('Nu au fost înregistrate evenimente noi Display/nvlddmkm/WHEA sau de suspendare în fereastra verificată.')
    lines += ['', 'Checkpointul original și fișierele datasetului au fost reverificate prin SHA256. Nu s-au instalat pachete și nu s-au descărcat modele/date. Checkpointurile noi sunt `finetuned-tf32.pth`, `finetuned-bf16.pth` și `finetuned-fp16.pth`, în acest director.', '',
        'Rezultatul demonstrează o epocă de fine-tuning pe acest model și dataset, nu convergența unei antrenări noi sau stabilitatea în toate aplicațiile. Un singur parcurs per precizie nu reprezintă o comparație statistică de acuratețe.', '',
        'Date: `training-summary.json`, `training-review.json`, `*-steps.jsonl`, `*-result.json`, `telemetry.jsonl`, `health-final.json`, `source/` și `training-order.npy`.', '',
        'Implementarea AMP urmează [exemplele PyTorch 2.8](https://github.com/pytorch/pytorch/blob/v2.8.0/docs/source/notes/amp_examples.rst), iar opțiunile TF32 urmează [notele CUDA pentru aceeași versiune](https://github.com/pytorch/pytorch/blob/v2.8.0/docs/source/notes/cuda.rst).', '']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    result=review(args.directory.resolve())
    print(json.dumps({'measurement_passed':result['measurement_passed'],'checks':result['checks'],
                      'hardware_events':len(result['hardware_events'])},indent=2))
    raise SystemExit(0 if result['measurement_passed'] else 1)
