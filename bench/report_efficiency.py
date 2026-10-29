"""Report the energy experiment without treating a short tuning trial as certification."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics


def review(directory):
    out = Path(directory)
    state = json.loads((out / 'efficiency-summary.json').read_text(encoding='utf-8-sig'))
    rows = [json.loads(line) for line in (out / 'energy-blocks.jsonl').read_text().splitlines()] if (out / 'energy-blocks.jsonl').exists() else []
    checks = dict(workload_completed=state['completed'], all_output_checks_passed=bool(rows) and all(r['correctness_passed'] for r in rows))
    initial = json.loads((out / 'inventory-before.json').read_text())
    final = json.loads((out / 'inventory-after.json').read_text())
    checks['final_offsets_match_initial'] = initial['graphics_offsets'] == final['graphics_offsets'] and initial['memory_offset'] == final['memory_offset']
    health = out / 'health-after.json'
    checks['no_unexpected_hardware_events'] = health.exists() and not json.loads(health.read_text())['events']
    if state['trial_requested']:
        checks['original_offsets_restored'] = state.get('offsets_restored_verified', False)
        watcher = out / 'watchdog-result.json'
        checks['independent_restoration_verified'] = watcher.exists() and json.loads(watcher.read_text()).get('verified', False)
    comparisons = []
    for offset, neighbors in [(30, ('reference-0', 'reference-1')), (60, ('reference-1', 'reference-2'))]:
        for mode in ('fp16', 'bf16'):
            measured = [r for r in state['results'] if r['phase'] == f'trial-{offset}' and r['mode'] == mode]
            controls = [r for r in state['results'] if r['phase'] in neighbors and r['mode'] == mode]
            if len(measured) != 1 or len(controls) != 2:
                continue
            trial = measured[0]
            power_comparable = all(abs(trial['average_power_w'] / c['average_power_w'] - 1) <= .03 for c in controls)
            temperature_comparable = all(abs(trial['max_temperature_c'] - c['max_temperature_c']) <= 3 for c in controls)
            lower_gain = min((trial['tflop_per_joule'] / c['tflop_per_joule'] - 1) * 100 for c in controls)
            comparisons.append(dict(offset_mhz=offset, mode=mode,
                efficiency_gain_vs_each_neighbor_percent=[(trial['tflop_per_joule'] / c['tflop_per_joule'] - 1) * 100 for c in controls],
                power_within_three_percent=power_comparable, temperature_within_three_c=temperature_comparable,
                promising_for_longer_validation=power_comparable and temperature_comparable and lower_gain > 1))
    result = dict(passed=all(checks.values()), checks=checks, comparisons=comparisons,
        automatic_persistent_tuning_applied=False,
        conclusion='A short screen identifies candidates only; no all-application or long-term tuning validation')
    (out / 'efficiency-review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    lines = ['# Eficiență FP16/BF16 și reglaj temporar', '',
        f"Stare: **{state['status']}**. Verificări complete: **{'PASS' if result['passed'] else 'INCOMPLETE'}**.", '',
        'Energia este diferența contorului NVML, în aceeași fereastră care încadrează GEMM-urile măsurate. '
        'Copierea și verificarea ieșirii se fac după citirea finală a energiei. TFLOP/J are aceeași dimensiune ca TFLOPS/W.', '',
        'Contorul descrie GPU-ul, inclusiv orice altă activitate simultană; nu măsoară consumul laptopului la priză.', '',
        '| Etapă | Mod | TFLOPS CUDA | W medii din energie | TFLOP/J | MHz mediană | mV mediană | Max. °C |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    if not state['trial_requested']:
        lines[4:4] = ['Sfera rezultatului: **referință energetică la setările existente; testul +30/+60 MHz nu a rulat**.', '']
        if (out / 'elevation-attempt.json').exists():
            lines[6:6] = ['Cererea UAC pentru reglajul temporar a fost anulată. Niciun offset nu a fost aplicat.', '']
    for row in state['results']:
        voltage = f"{row['median_voltage_mv']:.2f}" if row['median_voltage_mv'] is not None else 'N/A'
        lines.append(f"| {row['phase']} | {row['mode'].upper()} | {row['cuda_tflops']:.3f} | {row['average_power_w']:.2f} | {row['tflop_per_joule']:.4f} | {row['median_sm_clock_mhz']:.0f} | {voltage} | {row['max_temperature_c']:.0f} |")
    if state.get('error'):
        lines += ['', 'Motivul opririi: ' + state['error']]
    lines += ['', f"GEMM-uri măsurate: {sum(r['iterations'] for r in rows):,}. Blocuri verificate: {len(rows)}.", '',
        'Offseturile +30/+60 MHz modifică relația frecvență/tensiune; nu sunt o tensiune fixă sau un undervolt certificat. '
        'Nu se scriu tensiuni, limite de putere, frecvențe VRAM, firmware sau setări de pornire.', '',
        f"Restaurare/verificare finală a offseturilor: {state.get('offsets_restored_verified', checks['final_offsets_match_initial'])}.", '',
        'O îmbunătățire este doar candidat pentru testare lungă dacă depășește ambele referințe vecine cu peste 1%, '
        'cu puterea în ±3% și temperatura maximă în ±3°C. Acest criteriu este un filtru practic, nu o analiză de semnificație statistică.', '',
        'Curba exportată folosește o interfață privată numai pentru citire. Sunt capturate primele 80 de puncte; '
        'nu este garantat că acestea formează curba completă. Curba poate varia cu temperatura.', '',
        'Referința de aici este un test scurt, cu GPU mai rece decât în testul de 20 de minute. '
        'Diferența de TFLOPS față de testul lung nu reprezintă un câștig de reglaj.', '',
        'Niciun profil suplimentar de reglaj nu a fost instalat pentru aplicare automată.']
    for comparison in comparisons:
        gains = ', '.join(f'{v:+.2f}%' for v in comparison['efficiency_gain_vs_each_neighbor_percent'])
        lines += ['', f"+{comparison['offset_mhz']} MHz, {comparison['mode'].upper()}: eficiență față de referințele vecine {gains}; "
            f"candidat pentru test lung: {'DA' if comparison['promising_for_longer_validation'] else 'NU'}."]
    (out / 'EFFICIENCY-REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for name in ('before', 'after'):
        path = out / f'curve-{name}.json'
        if path.exists():
            curve = json.loads(path.read_text())
            with (out / f'curve-{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=['index', 'frequency_mhz', 'voltage_mv'])
                writer.writeheader(); writer.writerows(curve['points'])
    manifest = {str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in out.rglob('*') if path.is_file() and path.name != 'efficiency-manifest.json'}
    (out / 'efficiency-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(review(arguments.directory), indent=2))
