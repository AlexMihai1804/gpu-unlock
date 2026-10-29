"""Fine-tune an existing local CIFAR-100 ResNet50; no downloads/device setters.

Three independent one-epoch runs start from the same local checkpoint.
Original project/checkpoint/data are read-only; outputs belong to results/.
"""
import argparse
import contextlib
import ctypes as ct
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import threading
import time
import traceback

import numpy as np
import torch
from torch import nn
import torchvision
from torchvision import transforms as T

from endurance import ROOT, ac_power, read_health, save, utc
from nvidia_metrics import Nvml

PROJECT = Path(os.environ.get('CIFAR100_PROJECT', str(ROOT / 'local-data/cifar100')))
CHECKPOINT = PROJECT / 'day_5/best_resnet50_cifar100_88_09.pth'
DATA = PROJECT / 'cifar'
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
MODES = ('tf32', 'bf16', 'fp16')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def seed(value=3060):
    random.seed(value)
    np.random.seed(value)
    torch.manual_seed(value)
    torch.cuda.manual_seed_all(value)


def worker_seed(worker_id):
    value = torch.initial_seed() % 2**32
    random.seed(value)
    np.random.seed(value)


def model_from_checkpoint(state):
    model = torchvision.models.resnet50(weights=None)
    model.conv1 = nn.Conv2d(3, 64, 3, stride=1, padding=1, bias=False)
    model.maxpool = nn.Identity()
    model.fc = nn.Sequential(nn.Dropout(.2), nn.Linear(2048, 100))
    model.load_state_dict(state, strict=True)
    return model.to('cuda', memory_format=torch.channels_last)


def precision(mode):
    torch.backends.cuda.matmul.allow_tf32 = mode == 'tf32'
    torch.backends.cudnn.allow_tf32 = mode == 'tf32'


def amp(mode):
    if mode == 'tf32':
        return contextlib.nullcontext()
    return torch.autocast('cuda', dtype=torch.bfloat16 if mode == 'bf16' else torch.float16)


@torch.no_grad()
def evaluate(model, loader, guard):
    # All accuracy comparisons use the same strict FP32 evaluation protocol.
    precision('fp32')
    model.eval()
    correct, loss_sum, count = 0, 0.0, 0
    start = time.perf_counter()
    for images, labels in loader:
        guard()
        images = images.to('cuda', memory_format=torch.channels_last, non_blocking=True)
        labels = labels.to('cuda', non_blocking=True)
        output = model(images)
        loss = nn.functional.cross_entropy(output, labels, reduction='sum')
        value = float(loss.item())
        if not math.isfinite(value):
            raise RuntimeError('Nonfinite validation loss')
        loss_sum += value
        correct += int((output.argmax(1) == labels).sum().item())
        count += labels.numel()
    return dict(examples=count, top1_percent=100 * correct / count,
                loss=loss_sum / count, wall_seconds=time.perf_counter() - start,
                precision='strict FP32')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=64, choices=(32, 64))
    parser.add_argument('--workers', type=int, default=2, choices=(0, 2))
    parser.add_argument('--expected-offset', type=int, default=0, choices=(0, 150))
    parser.add_argument('--train-examples', type=int, default=50000)
    parser.add_argument('--validation-examples', type=int, default=10000)
    parser.add_argument('--smoke', action='store_true', help='Eight train batches and 256 validation examples, all three modes')
    args = parser.parse_args()
    if not 512 <= args.train_examples <= 50000 or not 256 <= args.validation_examples <= 10000:
        parser.error('Train examples 512..50000; validation examples 256..10000')
    out = args.output_directory.resolve()
    if not out.is_relative_to(ROOT / 'results') or not out.is_dir():
        parser.error('Existing project results directory required')
    if (out / 'training-summary.json').exists():
        parser.error('Use a fresh directory')
    state = dict(utc=utc(), status='initializing', completed=False,
        model='existing CIFAR-100 ResNet50, 3x3 stem, no maxpool, dropout 0.2 head',
        checkpoint=str(CHECKPOINT), dataset=str(DATA), modes=list(MODES),
        configuration=dict(batch_size=args.batch_size, workers=args.workers,
            epochs_per_mode=1, seed=3060, learning_rate=.0001, momentum=.9,
            weight_decay=.0001, max_gradient_norm=1.0, smoke=args.smoke,
            expected_graphics_offset_mhz=args.expected_offset),
        augmentation='Original project: random horizontal flip, reflected random crop, TrivialAugmentWide, ImageNet normalization',
        source_project=str(PROJECT / 'day_5/cifar100_resnet50.py'),
        original_files_modified=False, packages_installed=False,
        gpu_configuration_changed=False, temperature_cutoff=None, runs=[],
        scope=f'Precision comparison at {args.expected_offset} MHz offset; no locked-GPU stock comparison')
    save(out / 'training-summary.json', state)
    stop = threading.Event()
    phase, failures = ['initialization'], []
    telemetry, hardware_events = [], {}
    meter = None
    worker = None

    def guard():
        if failures:
            raise RuntimeError('; '.join(failures))
        if ac_power() != 1 or (out / 'STOP').exists():
            raise RuntimeError('AC disconnected or STOP requested')

    def monitor():
        last_health = 0.0
        def report_error(event):
            event.update(utc=utc(), phase=phase[0])
            with (out / 'telemetry-errors.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(event) + '\n')
        try:
            with (out / 'telemetry.jsonl').open('x', encoding='utf-8') as log:
                while not stop.is_set():
                    sample = meter.sample_with_retry(report_error, delay_seconds=.5)
                    sample.update(utc=utc(), phase=phase[0])
                    telemetry.append(sample)
                    log.write(json.dumps(sample) + '\n'); log.flush()
                    if time.monotonic() - last_health > 25:
                        health = read_health(state['utc'])
                        save(out / 'health-latest.json', health)
                        for event in health['events']:
                            hardware_events[str(event.get('record_id', event['utc']))] = event
                            corrected = (event['provider'] == 'Microsoft-Windows-WHEA-Logger'
                                         and event['id'] == 17
                                         and event.get('fields', {}).get('UncorrectableErrorStatus') == '0x0')
                            if not corrected:
                                failures.append('Driver/hardware/sleep event: ' + json.dumps(event))
                        last_health = time.monotonic()
                    if ac_power() != 1:
                        failures.append('AC disconnected')
                    stop.wait(.5)
        except BaseException as error:
            failures.append(str(error))

    try:
        if not torch.cuda.is_available() or torch.cuda.get_device_capability(0) != (8, 6):
            raise RuntimeError('Expected CUDA Ampere laptop GPU')
        if not torch.cuda.is_bf16_supported():
            raise RuntimeError('BF16 unavailable')
        meter = Nvml()
        inventory = meter.inventory()
        save(out / 'inventory-before.json', inventory)
        if any(row['offset'] != args.expected_offset for row in inventory['graphics_offsets'].values()) or inventory['memory_offset']['offset'] != 0:
            raise RuntimeError('Graphics offset differs from expected value, or memory offset is not zero')
        state.update(torch=torch.__version__, torchvision=torchvision.__version__,
            cuda_runtime=torch.version.cuda, cudnn=torch.backends.cudnn.version(),
            device=torch.cuda.get_device_name(0), checkpoint_sha256=digest(CHECKPOINT),
            source_sha256=digest(Path(__file__)), dataset_hashes={
                name:digest(DATA / 'cifar-100-python' / name) for name in ('train', 'test', 'meta')})
        initial = torch.load(CHECKPOINT, map_location='cpu', weights_only=True)
        train_transform = T.Compose([T.RandomHorizontalFlip(), T.RandomCrop(32, padding=4, padding_mode='reflect'),
            T.TrivialAugmentWide(), T.PILToTensor(), T.ConvertImageDtype(torch.float32), T.Normalize(MEAN, STD)])
        test_transform = T.Compose([T.PILToTensor(), T.ConvertImageDtype(torch.float32), T.Normalize(MEAN, STD)])
        train_data = torchvision.datasets.CIFAR100(str(DATA), train=True, download=False, transform=train_transform)
        test_data = torchvision.datasets.CIFAR100(str(DATA), train=False, download=False, transform=test_transform)
        generator = torch.Generator().manual_seed(3060)
        order = torch.randperm(len(train_data), generator=generator)
        order = order[:args.train_examples]
        if args.validation_examples < len(test_data):
            test_data = torch.utils.data.Subset(test_data, range(args.validation_examples))
        if args.smoke:
            order = order[:8 * args.batch_size]
            test_data = torch.utils.data.Subset(test_data, range(256))
        np.save(out / 'training-order.npy', order.numpy())
        state['training_order_sha256'] = digest(out / 'training-order.npy')
        state['train_examples_per_mode'], state['validation_examples'] = len(order), len(test_data)
        torch.set_num_threads(4)
        torch.backends.cudnn.benchmark = True
        if not ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000003)):
            raise RuntimeError('Cannot inhibit idle sleep')
        worker = threading.Thread(target=monitor, daemon=True)
        worker.start()
        guard()
        validation = torch.utils.data.DataLoader(test_data, batch_size=128, shuffle=False,
            num_workers=0, pin_memory=True)
        model = model_from_checkpoint(initial)
        phase[0] = 'baseline-validation'
        print('Initial checkpoint: strict FP32 validation', flush=True)
        state['baseline_validation'] = evaluate(model, validation, guard)
        print(json.dumps(state['baseline_validation']), flush=True)
        state['parameters'] = sum(p.numel() for p in model.parameters())
        save(out / 'training-summary.json', state)
        del model
        torch.cuda.empty_cache()
        for mode in MODES:
            guard(); seed()
            model = model_from_checkpoint(initial)
            precision(mode)
            model.train()
            phase[0] = mode + '-warmup'
            images = torch.stack([train_data[i][0] for i in range(args.batch_size)]).to('cuda', memory_format=torch.channels_last)
            labels = torch.tensor([train_data[i][1] for i in range(args.batch_size)], device='cuda')
            # Warm kernels without optimizer updates, then restore BN buffers and RNG.
            with amp(mode):
                loss = nn.functional.cross_entropy(model(images), labels)
            loss.backward()
            torch.cuda.synchronize()
            model.load_state_dict(initial, strict=True)
            model.zero_grad(set_to_none=True)
            del images, labels, loss
            seed()
            loader = torch.utils.data.DataLoader(torch.utils.data.Subset(train_data, order.tolist()),
                batch_size=args.batch_size, shuffle=False, num_workers=args.workers, pin_memory=True,
                worker_init_fn=worker_seed, generator=torch.Generator().manual_seed(3060))
            optimizer = torch.optim.SGD(model.parameters(), lr=.0001, momentum=.9, weight_decay=.0001)
            scaler = torch.amp.GradScaler('cuda', enabled=mode == 'fp16', init_scale=1024)
            start_event, end_event = [torch.cuda.Event(enable_timing=True) for _ in range(2)]
            torch.cuda.reset_peak_memory_stats()
            rows = []; count = 0; loss_sum = 0.0; correct = 0; data_wait = 0.0
            phase[0] = mode + '-train'
            torch.cuda.synchronize(); started = time.perf_counter(); previous = started
            print(f'TRAIN {mode}: {len(order)} examples, batch {args.batch_size}', flush=True)
            with (out / f'{mode}-steps.jsonl').open('x', encoding='utf-8') as log:
                for step, (images, labels) in enumerate(loader):
                    ready = time.perf_counter(); data_wait += ready - previous; guard()
                    images = images.to('cuda', memory_format=torch.channels_last, non_blocking=True)
                    labels = labels.to('cuda', non_blocking=True)
                    optimizer.zero_grad(set_to_none=True)
                    start_event.record()
                    with amp(mode):
                        output = model(images)
                        loss = nn.functional.cross_entropy(output, labels)
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    gradient_norm = nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
                    scaler.step(optimizer); scaler.update()
                    end_event.record(); end_event.synchronize()
                    loss_value = float(loss.item())
                    if not math.isfinite(loss_value):
                        raise RuntimeError('Nonfinite training loss')
                    size = labels.numel(); count += size; loss_sum += loss_value * size
                    correct += int((output.detach().argmax(1) == labels).sum().item())
                    row = dict(step=step, examples=size, loss=loss_value, gradient_norm=float(gradient_norm.item()),
                        cuda_stream_ms=start_event.elapsed_time(end_event),
                        wall_step_seconds=time.perf_counter()-ready, scaler_scale=scaler.get_scale())
                    rows.append(row); log.write(json.dumps(row)+'\n'); log.flush()
                    if (step+1) % 50 == 0 or count == len(order):
                        progress = dict(utc=utc(), mode=mode, step=step+1, examples=count,
                            total_examples=len(order), loss=loss_sum/count, train_top1_percent=100*correct/count,
                            images_per_second=count/(time.perf_counter()-started))
                        save(out / 'progress.json', progress); print(json.dumps(progress), flush=True)
                    previous = time.perf_counter()
            torch.cuda.synchronize(); wall = time.perf_counter()-started
            run = dict(mode=mode, examples=count, steps=len(rows), wall_seconds=wall,
                images_per_second=count/wall, data_wait_seconds=data_wait,
                median_cuda_stream_step_ms=statistics.median(r['cuda_stream_ms'] for r in rows),
                train_loss=loss_sum/count, train_top1_percent=100*correct/count,
                first_50_batch_loss=statistics.mean(r['loss'] for r in rows[:50]),
                last_50_batch_loss=statistics.mean(r['loss'] for r in rows[-50:]),
                peak_allocated_mib=torch.cuda.max_memory_allocated()/2**20,
                peak_reserved_mib=torch.cuda.max_memory_reserved()/2**20,
                finite_gradients_checked_every_step=True,
                all_parameters_finite=all(bool(torch.isfinite(p).all()) for p in model.parameters()),
                classifier_weight_change_l2=float(torch.linalg.vector_norm(model.fc[1].weight.detach().cpu()-initial['fc.1.weight'])),
                optimizer_step_count=len(rows), warmup_included_in_epoch_time=False)
            if not run['all_parameters_finite'] or run['classifier_weight_change_l2'] <= 0 or count != len(order):
                raise RuntimeError('Training parameter update validation failed')
            phase[0] = mode + '-validation'
            run['validation'] = evaluate(model, validation, guard)
            checkpoint = out / f'finetuned-{mode}.pth'
            torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()}, checkpoint)
            run['checkpoint'], run['checkpoint_sha256'] = str(checkpoint), digest(checkpoint)
            active = [s for s in telemetry if s['phase']==mode+'-train' and s['utilization_percent']>=90]
            run['telemetry'] = dict(active_samples=len(active), median_power_w=statistics.median(s['power_w'] for s in active) if active else None,
                median_sm_mhz=statistics.median(s['sm_clock_mhz'] for s in active) if active else None,
                maximum_temperature_c=max((s['temperature_c'] for s in telemetry if s['phase']==mode+'-train'),default=None))
            state['runs'].append(run)
            save(out / f'{mode}-result.json', run)
            save(out / 'training-summary.json', state)
            print('FINISHED '+json.dumps(run), flush=True)
            del model, optimizer, scaler, output, loss, images, labels, gradient_norm
            torch.cuda.empty_cache()
        guard()
        if digest(CHECKPOINT) != state['checkpoint_sha256']:
            raise RuntimeError('Original checkpoint changed')
        state.update(status='passed', completed=True, original_checkpoint_unchanged=True)
    except BaseException as error:
        state.update(status='stopped', completed=False, error=str(error), traceback=traceback.format_exc())
        print('STOPPED '+str(error), flush=True)
    finally:
        stop.set()
        if worker is not None:
            worker.join(timeout=25)
        if meter is not None:
            final = meter.inventory(); save(out/'inventory-after.json', final); meter.close()
            state['final_offsets_zero'] = all(v['offset']==0 for v in final['graphics_offsets'].values()) and final['memory_offset']['offset']==0
            state['final_offsets_match_expected'] = all(v['offset']==args.expected_offset for v in final['graphics_offsets'].values()) and final['memory_offset']['offset']==0
        ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000000))
        state.update(finished_utc=utc(), maximum_temperature_c=max((s['temperature_c'] for s in telemetry),default=None),
                     hardware_events=list(hardware_events.values()))
        save(out / 'training-summary.json', state)
    return 0 if state['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
