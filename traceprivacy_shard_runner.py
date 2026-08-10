from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], env: dict[str, str]) -> None:
    print('RUN', ' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--target', choices=['tradingagents', 'swarm'], required=True)
    p.add_argument('--scenario-id', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--tradingagents-repo', type=Path, required=True)
    p.add_argument('--swarm-repo', type=Path, required=True)
    a = p.parse_args()
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        raise SystemExit('DEEPSEEK_API_KEY required')
    a.output.mkdir(parents=True, exist_ok=True)
    from trace_privacy.common import PRIMARY_MODEL, deepseek_probe, json_dump, write_hash_manifest
    json_dump(a.output / 'probe.json', deepseek_probe(key))
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    if a.target == 'tradingagents':
        records = a.output / 'tradingagents_records.json'
        run([sys.executable, '-m', 'trace_privacy.tradingagents_runner', '--output', str(a.output), '--repo', str(a.tradingagents_repo), '--scenario-ids', a.scenario_id], env)
        system = 'TradingAgents'
    else:
        records = a.output / 'swarm_records.json'
        run([sys.executable, '-m', 'trace_privacy.swarm_runner', '--output', str(a.output), '--repo', str(a.swarm_repo), '--scenario-ids', a.scenario_id], env)
        system = 'swarm-trader'
    run([sys.executable, '-m', 'trace_privacy.single_baseline_runner', '--output', str(a.output), '--mas-records', str(records)], env)
    probe = load(a.output / 'probe.json')
    mas = load(records)
    single = load(a.output / 'single_records.json')
    errors: list[str] = []
    if probe.get('requested_model') != PRIMARY_MODEL or probe.get('returned_model') != PRIMARY_MODEL:
        errors.append(f'model identity mismatch: {probe}')
    if len(mas) != 1 or len(single) != 1:
        errors.append(f'expected one MAS and one single record, got {len(mas)} and {len(single)}')
    for kind, group in [('MAS', mas), ('single', single)]:
        for record in group:
            if not record.get('hard_valid'):
                errors.append(f'{kind}: hard_valid=false error={record.get("error")}')
            if not record.get('packets'):
                errors.append(f'{kind}: empty packet trace')
            if not record.get('app_calls'):
                errors.append(f'{kind}: empty app trace')
            if any((not c.get('ok')) or c.get('returned_model') != PRIMARY_MODEL for c in record.get('app_calls', [])):
                errors.append(f'{kind}: failed/wrong-model call')
            pcap = Path(record.get('pcap_path', '')) if record.get('pcap_path') else None
            if pcap is not None and not pcap.exists():
                errors.append(f'{kind}: pcap path missing')
    if mas and mas[0].get('scenario', {}).get('scenario_id') != a.scenario_id:
        errors.append('MAS scenario mismatch')
    if single and single[0].get('matched_to_scenario') != a.scenario_id:
        errors.append('single scenario mismatch')
    if single and single[0].get('system') != system:
        errors.append('single system mismatch')
    audit = {
        'completed': not errors,
        'target': a.target,
        'system': system,
        'scenario_id': a.scenario_id,
        'errors': errors,
        'probe': probe,
        'mas_action': mas[0].get('action_label') if mas else None,
        'single_action': single[0].get('action_label') if single else None,
        'mas_calls': len(mas[0].get('app_calls', [])) if mas else 0,
        'single_calls': len(single[0].get('app_calls', [])) if single else 0,
        'prompt_byte_ratio': single[0].get('matching', {}).get('prompt_byte_ratio') if single else None,
    }
    json_dump(a.output / 'SHARD_VERIFICATION.json', audit)
    write_hash_manifest(a.output, a.output / 'SHA256SUMS.txt')
    if errors:
        raise SystemExit('SHARD HARD VERIFICATION FAILED:\n' + '\n'.join(errors))
    (a.output / 'SHARD_COMPLETE_SUCCESS.marker').write_text('verified\n', encoding='utf-8')
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == '__main__':
    main()
