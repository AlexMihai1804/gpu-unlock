"""Offline review of the bounded four-mode ABBA offset experiment."""
import argparse
import hashlib
import json
from pathlib import Path

from compare import compare
from compare_offset150 import summarize
from endurance import known_network_warning
from performance_state import classify


def review(out):
    def read(name):
        return json.loads((out / name).read_text(encoding='utf-8-sig'))

    state = read('comparison-summary.json')
    computed = summarize(state['rounds'])
    start, end, independent = [read(name) for name in
        ('inventory-before.json', 'inventory-after.json', 'independent-final-inventory.json')]
    contexts = [read(name) for name in ('test-context.json', 'test-context-after.json', 'final-context.json')]
    health = read('health-after.json')
    before, after = read('before.json'), read('after.json')
    post_control = compare(before, after)
    post_state = classify(after)
    samples = [json.loads(line) for line in (out / 'telemetry.jsonl').read_text().splitlines()]
    offsets = [json.loads(line) for line in (out / 'offset-events.jsonl').read_text().splitlines()]
    source_hashes = {name: hashlib.sha256((out / 'source' / name).read_bytes()).hexdigest()
                     for name in state['source_sha256']}
    checks = dict(completed=state['completed'] and state['status'] == 'passed',
        recomputed_summary_matches=computed == state['comparison'],
        sources_match_measurement=source_hashes == state['source_sha256'],
        four_raw_round_files_match=all(read(f'round-{i}.json') == row for i, row in enumerate(state['rounds'])),
        original_offsets_restored=state.get('original_offsets_restored_verified', False),
        independent_watchdog=read('watchdog-result.json')['verified'],
        independent_offsets_restored=end['graphics_offsets'] == independent['graphics_offsets'] == start['graphics_offsets']
            and end['memory_offset'] == independent['memory_offset'] == start['memory_offset'],
        initial_offsets_zero=all(row['offset'] == 0 for row in start['graphics_offsets'].values()) and start['memory_offset']['offset'] == 0,
        ABBA_offsets_confirmed_by_readback=[row['requested_mhz'] for row in offsets] == [0, 150, 150, 0]
            and all(row['p0']['offset'] == row['p2']['offset'] == row['requested_mhz']
                    and row['memory'] == start['memory_offset'] for row in offsets),
        same_boot_secure_boot=len({row['windows_boot_utc'] for row in contexts}) == 1
            and all(row['secure_boot_registry'] == 1 for row in contexts),
        no_unexpected_hardware_or_driver_events=not [event for event in health['events'] if not known_network_warning(event)],
        final_matched_control_outputs_identical=all(row['output_bit_identical'] for row in post_control),
        final_FP16_BF16_TF32_unlocked_pattern=post_state.get('tf32_unlocked_performance_supported', False),
        no_persistent_tuning=not state['persistent_tuning_applied'],
        launcher_completed=(out / 'launcher-exit.txt').read_text().strip() == '0')
    bits = dict(sw_power_cap=4, sw_thermal_slowdown=32, hw_thermal_slowdown=64, hw_power_brake=128)
    limiters = {}
    for offset in (0, 150):
        active = [s for s in samples if s['offset_mhz'] == offset and s['utilization_percent'] >= 90]
        limiters[str(offset)] = dict(active_samples=len(active), sample_percent={name:
            100 * sum(bool(s['clocks_event_reasons'] & bit) for s in active) / len(active) if active else None
            for name, bit in bits.items()})
    measurement_passed = all(value for name, value in checks.items()
                             if name != 'no_unexpected_hardware_or_driver_events')
    result = dict(passed=all(checks.values()), measurement_passed=measurement_passed,
        hardware_health_clean=checks['no_unexpected_hardware_or_driver_events'],
        hardware_events=health['events'],
        comparison_window_hardware_events=read('health-after-comparison.json')['events'],
        checks=checks, comparison=computed,
        limiter_telemetry=limiters, maximum_temperature_c=state['maximum_temperature_c'],
        final_performance_state=post_state, final_matched_control=post_control,
        persistent_tuning_applied=False,
        scope='Same-boot fixed-input four-mode GEMM; unlock retained; zero vs +150 MHz; no all-application or sleep certification')
    (out / 'comparison-review.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    lines = ['# Comparație offset GPU 0 MHz / +150 MHz', '',
        f"**Performanță/corectitudine: {'PASS' if measurement_passed else 'INCOMPLETE'}. Verificare hardware finală: {'PASS' if result['hardware_health_clean'] else 'CU AVERTISMENT'}.** Unlock-ul FP16/BF16/TF32 a rămas activ. „Stock” în acest raport înseamnă offset GPU zero, cu unlock păstrat.", '',
        'Aceeași pornire, aceleași biblioteci și matrice dense 8192×8192. Ordine: **0 → +150 → +150 → 0 MHz**; fiecare rundă acoperă FP16, BF16, TF32 și FP32. Încălzire 6 s/mod, 7 probe × 30 GEMM/mod/rundă. Valorile de mai jos provin din mediana celor 14 timpi CUDA per configurație și mod.', '',
        '| Mod | Offset 0, TFLOPS | Offset +150, TFLOPS | Câștig | Control 0 final vs inițial |',
        '|---|---:|---:|---:|---:|']
    for mode, row in computed.items():
        lines.append(f"| {mode.upper()} | {row['offsets']['0']['tflops']:.3f} | {row['offsets']['150']['tflops']:.3f} | {row['gain_percent']:+.2f}% | {row['zero_last_vs_first_percent']:+.2f}% |")
    lines += ['', '## Rulări individuale', '',
        '| Rundă | Offset MHz | Mod | TFLOPS | Putere mediană activă, W | SM median, MHz | Max. °C |',
        '|---|---:|---|---:|---:|---:|---:|']
    for item in state['rounds']:
        for row in item['results']:
            telemetry = row['telemetry_summary']
            lines.append(f"| {item['round']+1} | {item['offset_mhz']} | {row['mode'].upper()} | {row['tflops']:.3f} | {telemetry['median_power_w']:.2f} | {telemetry['median_sm_mhz']:.0f} | {telemetry['maximum_temperature_c']} |")
    lines += ['', f"Temperatura maximă în toate eșantioanele: **{state['maximum_temperature_c']}°C**. Niciun prag artificial de oprire la temperatură.", '',
        'Puterea și frecvența sunt mediane din telemetria cu utilizare GPU ≥90%, incluzând încălzirea. Nu reprezintă energia exactă a probelor CUDA sau consumul laptopului la priză. Ordinea ABBA reduce influența unei derive simple, dar nu garantează temperaturi, Dynamic Boost sau limite de putere perfect identice.', '',
        '## Limitări raportate de NVIDIA', '']
    for offset, data in limiters.items():
        percentages = data['sample_percent']
        lines.append(f"- Offset {offset} MHz, {data['active_samples']} eșantioane active: Power Cap {percentages['sw_power_cap']:.2f}%; SW Thermal {percentages['sw_thermal_slowdown']:.2f}%; HW Thermal {percentages['hw_thermal_slowdown']:.2f}%; HW Power Brake {percentages['hw_power_brake']:.2f}%.")
    lines += ['', 'Procentele reprezintă eșantioane, nu împărțirea exactă a timpului CUDA.', '',
        '## Eveniment hardware după comparație', '']
    if result['hardware_events']:
        lines += [f"Evenimente în intervalul celor patru runde: {len(result['comparison_window_hardware_events'])}; în întreaga fereastră verificată: {len(result['hardware_events'])}.", '']
        for event in result['hardware_events']:
            fields = event.get('fields', {})
            lines += [f"- {event['utc']}: {event['provider']} {event['id']}, dispozitiv {fields.get('PrimaryDeviceName', '')}; status corectabil {fields.get('CorrectableErrorStatus', 'N/A')}, necorectabil {fields.get('UncorrectableErrorStatus', 'N/A')}."]
        warning_path = out / 'pcie-warning-review.json'
        if warning_path.exists():
            warning = read('pcie-warning-review.json')
            lines += ['',
                f"Ultima setare și citire 0 MHz: {warning['last_zero_offset_readback']['utc']}. Finalul comparației: {warning['comparison_finished_utc']}. Inițializarea controlului final: {warning['post_control_initialization_utc']}.", '',
                f"Evenimentul a apărut la {warning['event_after_last_zero_offset_seconds']:.1f} s după ultima setare zero și la {warning['event_after_comparison_seconds']:.1f} s după finalul comparației. Topologia PnP confirmă că portul 1022:14B8, 00:01.1 este părintele RTX 3060. Nu este avertismentul cunoscut al portului de rețea. Nu putem stabili mai precis starea GPU în fereastra dintre sfârșitul comparației și inițializarea controlului final.", '',
                f"Aceeași semnătură apare în {warning['same_signature_historical_events_before_tuning']} înregistrări istorice anterioare testelor de offset. Cauza nu este demonstrată; evenimentul rămâne în filtrul de sănătate. Dovezi: `pcie-warning-review.json`, `gpu-pcie-topology.json`, `health-after.json` și `historical-gpu-pcie-events.json`."]
        lines += ['', '**Câștigul măsurat nu oferă un verdict de stabilitate hardware complet curat. +150 MHz nu este aplicat permanent.**', '']
    else:
        lines += ['Nu au fost găsite evenimente hardware sau de driver noi în fereastra verificată.', '']
    lines += [
        '## Corectitudine și restaurare', '',
        'Toate cele 16 rezultate complete de mod/rundă sunt verificate prin SHA256 față de stock-ul original în precizia respectivă, plus 2.048 de valori comparate cu CPU FP64. Fiecare rezultat este ieșirea finală a unei runde; rezultatele intermediare nu sunt inspectate individual.', '',
        'Offseturile grafice și de memorie au revenit la zero, verificate de procesul principal, de watchdog și printr-o citire independentă. Benchmarkul final la zero păstrează profilul FP16/BF16/TF32 deblocat. Secure Boot rămâne activ în aceeași pornire. Nu s-au modificat tensiuni, limita de putere, memoria, firmware-ul sau configurația de boot; nu este aplicat un profil permanent.', '',
        'Date și verificări: `comparison-review.json`, `comparison-summary.json`, `round-0.json` … `round-3.json`, `telemetry.jsonl`, `offset-events.jsonl`, `watchdog-result.json`, `independent-final-inventory.json`, `before.json`, `after.json` și `source/`.', '',
        'Acest test arată câștigul în GEMM pentru condițiile măsurate; nu certifică stabilitatea în toate aplicațiile sau după sleep/resume. Stock-ul original fără unlock rămâne o măsurare istorică separată în `../baseline-2026-10-25.json`.', '']
    (out / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = review(args.directory)
    print(json.dumps({'passed': result['passed'], 'checks': result['checks'],
                      'comparison': result['comparison']}, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
