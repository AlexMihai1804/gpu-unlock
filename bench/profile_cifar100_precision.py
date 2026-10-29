"""Trace three isolated training steps to explain precision/backend differences.

Run only after the full training process has exited. No device setters or saved
model updates; this profile is separate from unprofiled epoch measurements.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics

import torch
from torch import nn
import torchvision
from torchvision import transforms as T

from train_existing_cifar100 import CHECKPOINT, DATA, MEAN, STD, MODES, amp, model_from_checkpoint, precision, seed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',type=Path,required=True)
    args=parser.parse_args()
    out=args.output_directory.resolve()
    if not out.is_dir() or not (out/'training-summary.json').exists():
        parser.error('Completed experiment directory required')
    state=json.loads((out/'training-summary.json').read_text())
    if not state['completed']:
        parser.error('Training must finish before profiling')
    traces=out/'precision-profiles'
    traces.mkdir()
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark=True
    transform=T.Compose([T.PILToTensor(),T.ConvertImageDtype(torch.float32),T.Normalize(MEAN,STD)])
    data=torchvision.datasets.CIFAR100(str(DATA),train=False,download=False,transform=transform)
    images=torch.stack([data[i][0] for i in range(64)]).to('cuda',memory_format=torch.channels_last)
    labels=torch.tensor([data[i][1] for i in range(64)],device='cuda')
    original=torch.load(CHECKPOINT,map_location='cpu',weights_only=True)
    result={}
    for mode in MODES:
        seed(); precision(mode)
        model=model_from_checkpoint(original);model.train()
        optimizer=torch.optim.SGD(model.parameters(),lr=.0001,momentum=.9,weight_decay=.0001)
        scaler=torch.amp.GradScaler('cuda',enabled=mode=='fp16',init_scale=1024)
        def step():
            optimizer.zero_grad(set_to_none=True)
            with amp(mode):
                loss=nn.functional.cross_entropy(model(images),labels)
            scaler.scale(loss).backward();scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True)
            scaler.step(optimizer);scaler.update()
            return float(loss.item())
        for _ in range(3):step()
        timings=[]
        for _ in range(3):
            start,end=[torch.cuda.Event(enable_timing=True) for _ in range(2)]
            start.record();step();end.record();end.synchronize()
            timings.append(start.elapsed_time(end))
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,
                torch.profiler.ProfilerActivity.CUDA]) as profile:
            for _ in range(3):
                with torch.profiler.record_function(mode+'-training-step'):step()
                profile.step()
            torch.cuda.synchronize()
        trace=traces/(mode+'.json');profile.export_chrome_trace(str(trace))
        events=json.loads(trace.read_text(encoding='utf-8'))['traceEvents']
        kernels=defaultdict(lambda:dict(calls=0,total_us=0.))
        for event in events:
            if event.get('cat')=='kernel':
                row=kernels[event['name']];row['calls']+=1;row['total_us']+=event.get('dur',0.)
        result[mode]=dict(unprofiled_gpu_resident_step_ms=timings,
            median_unprofiled_step_ms=statistics.median(timings),
            traced_steps=3,kernel_calls=sum(row['calls'] for row in kernels.values()),
            top_kernels=sorted([dict(name=name,**row) for name,row in kernels.items()],key=lambda row:row['total_us'],reverse=True)[:15],
            flags=dict(matmul_tf32=torch.backends.cuda.matmul.allow_tf32,cudnn_tf32=torch.backends.cudnn.allow_tf32))
        print(mode,json.dumps(result[mode]),flush=True)
        del model,optimizer,scaler
        torch.cuda.empty_cache()
    (traces/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
