"""Review adaptive offset evidence; execution PASS is separate from tuning value."""
import argparse
import hashlib
import json
from pathlib import Path


def review(out):
    state=json.loads((out/'adaptive-summary.json').read_text())
    rows=[json.loads(line) for line in (out/'energy-blocks.jsonl').read_text().splitlines()] if (out/'energy-blocks.jsonl').exists() else []
    checks={'completed':state['completed'],'all_final_block_outputs_correct':bool(rows) and all(r['correctness_passed'] for r in rows),
        'original_offsets_restored':state.get('original_offsets_restored_verified',False)}
    for name,key in [('watchdog-result.json','independent_watchdog_verification'),('independent-final-readback.json','independent_final_readback')]:
        p=out/name;checks[key]=p.exists() and json.loads(p.read_text()).get('verified',False)
    p=out/'health-after.json';checks['no_unexpected_events']=p.exists() and not json.loads(p.read_text())['events']
    contexts=[out/n for n in ('test-context.json','test-context-after.json')]
    if all(p.exists() for p in contexts):
        before,after=[json.loads(p.read_text(encoding='utf-8-sig')) for p in contexts]
        checks['same_boot_secure_boot_enabled']=before['windows_boot_utc']==after['windows_boot_utc'] and before['secure_boot_registry']==after['secure_boot_registry']==1
    else:
        checks['same_boot_secure_boot_enabled']=False
    validation=state.get('long_validation')
    if state['selected_offset_mhz']:
        duration=next((p['measured_cuda_seconds'] for p in state['phases'] if p['label']==f"validation-{state['selected_offset_mhz']}"),0)
        checks['ten_minutes_measured_cuda_validation']=duration>=600
    passed=all(checks.values())
    recommended=state['selected_offset_mhz'] if passed and validation and validation['worth'] and validation['stable_throughput'] else 0
    result={'passed':passed,'checks':checks,'best_screened_offset_mhz':state['selected_offset_mhz'],
        'validated_candidate_mhz':recommended,'persistent_tuning_applied':False,
        'scope':'Fixed-input dense GEMM only; one boot, no all-application, idle or sleep certification'}
    (out/'adaptive-review.json').write_text(json.dumps(result,indent=2))
    lines=['# Test adaptiv al offsetului GPU','',f"Execuție: **{'PASS' if passed else 'INCOMPLETE'}**. Stare: {state['status']}.",'',
        f"Candidat susținut de validarea lungă: **+{recommended} MHz**." if recommended else 'Nu este demonstrat un candidat pentru aplicare permanentă.', '',
        '| Etapă | Offset MHz | Mod | TFLOPS | TFLOP/J | W medii | Max. °C | CUDA s |',
        '|---|---:|---|---:|---:|---:|---:|---:|']
    for phase in state['phases']:
        for mode,m in phase['modes'].items():
            lines.append(f"| {phase['label']} | {phase['offset_mhz']} | {mode.upper()} | {m['tflops']:.3f} | {m['efficiency']:.4f} | {m['power_w']:.2f} | {m['max_temperature_c']:.0f} | {m['cuda_seconds']:.1f} |")
    lines+=['',f"Blocuri măsurate/verificate: {state['blocks']}; GEMM-uri: {state['gemm_count']:,}; temperatură maximă: {state['max_temperature_c']}°C.",'',
        'Se verifică ieșirea finală integrală a fiecărui bloc și 2.048 de valori CPU FP64, nu toate rezultatele intermediare.', '',
        'Energia este diferența contorului GPU pentru aceeași fereastră care încadrează GEMM-urile; copierea și validarea CPU sunt excluse. Nu este consumul laptopului la priză.', '',
        'Fiecare creștere cere un câștig de eficiență >1% și de debit >0,5% față de fiecare referință vecină, pentru ambele moduri. '
        'Puterea trebuie să fie în ±3%, iar temperatura maximă în ±3°C. Pentru următorul pas se cere și un câștig marginal >0,5% în ambele moduri. '
        'Acestea sunt filtre practice, nu teste de semnificație statistică. Nu există prag artificial de oprire la temperatură.', '',
        f"Restaurarea offseturilor inițiale: {state.get('original_offsets_restored_verified',False)}. Niciun profil suplimentar nu este aplicat la pornire.",'']
    for d in state['decisions']:
        lines.append(f"+{d['offset_mhz']} MHz: merită în comparația cu 0 MHz: {d['worth']}; progresie justificată față de pasul precedent: {d['allow_next_step']}.")
        for mode,m in d['modes'].items():
            lines.append(f"- {mode.upper()}: eficiență {m['efficiency_gain_percent']:+.2f}%; față de fiecare control {m['efficiency_gain_each_percent']}; câștig marginal {m['marginal_efficiency_percent']}%.")
        lines.append('')
    if validation:
        lines+=['Validarea de 10 minute CUDA, față de referințele vecine:','']
        for mode,m in validation['modes'].items():
            lines.append(f"- {mode.upper()}: {m['current']['tflops']:.3f} TFLOPS, eficiență {m['efficiency_gain_percent']:+.2f}%, ultimul vs primul sfert {m['last_vs_first_quarter_percent']:+.2f}%.")
    if state.get('error'):
        lines+=['','Motivul opririi: '+state['error']]
    lines+=['','Rezultatul nu certifică toate aplicațiile, persistența după suspendare sau un undervolt universal. Nu se modifică tensiuni fixe, limita de putere, VRAM, firmware sau cheia de încredere Secure Boot.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'evidence-manifest.json').write_text(json.dumps({str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='evidence-manifest.json'},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);args=p.parse_args()
    print(json.dumps(review(args.directory),indent=2))
