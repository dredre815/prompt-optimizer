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
    p=argparse.ArgumentParser()
    p.add_argument('--target',choices=['tradingagents','swarm'],required=True)
    p.add_argument('--ticker',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tradingagents-repo',type=Path,required=True)
    p.add_argument('--swarm-repo',type=Path,required=True)
    a=p.parse_args()
    key=os.environ.get('DEEPSEEK_API_KEY')
    if not key: raise SystemExit('DEEPSEEK_API_KEY required')
    a.output.mkdir(parents=True,exist_ok=True)
    from trace_privacy.common import PRIMARY_MODEL, deepseek_probe, generate_scenarios, json_dump, write_hash_manifest
    scenario_ids=[s.scenario_id for s in generate_scenarios() if s.ticker==a.ticker]
    if len(scenario_ids)!=6: raise SystemExit(f'expected six scenarios for {a.ticker}, got {scenario_ids}')
    json_dump(a.output/'probe.json',deepseek_probe(key))
    env=os.environ.copy(); env['PYTHONUNBUFFERED']='1'
    if a.target=='tradingagents':
        records=a.output/'tradingagents_records.json'; system='TradingAgents'
        run([sys.executable,'-m','trace_privacy.tradingagents_runner','--output',str(a.output),'--repo',str(a.tradingagents_repo),'--scenario-ids',','.join(scenario_ids)],env)
    else:
        records=a.output/'swarm_records.json'; system='swarm-trader'
        run([sys.executable,'-m','trace_privacy.swarm_runner','--output',str(a.output),'--repo',str(a.swarm_repo),'--scenario-ids',','.join(scenario_ids)],env)
    run([sys.executable,'-m','trace_privacy.single_baseline_runner','--output',str(a.output),'--mas-records',str(records)],env)
    probe=load(a.output/'probe.json'); mas=load(records); single=load(a.output/'single_records.json')
    errors=[]
    if probe.get('requested_model')!=PRIMARY_MODEL or probe.get('returned_model')!=PRIMARY_MODEL: errors.append('model identity mismatch')
    if len(mas)!=6 or len(single)!=6: errors.append(f'expected 6+6 records, got {len(mas)}+{len(single)}')
    expected=set(scenario_ids)
    if {r.get('scenario',{}).get('scenario_id') for r in mas}!=expected: errors.append('MAS scenario set mismatch')
    if {r.get('matched_to_scenario') for r in single}!=expected: errors.append('single scenario set mismatch')
    for kind,group in [('MAS',mas),('single',single)]:
        for r in group:
            sid=r.get('scenario',{}).get('scenario_id') if kind=='MAS' else r.get('matched_to_scenario')
            if not r.get('hard_valid'): errors.append(f'{kind}/{sid}: hard_valid=false: {r.get("error")}')
            if not r.get('packets'): errors.append(f'{kind}/{sid}: empty packets')
            if not r.get('app_calls'): errors.append(f'{kind}/{sid}: empty calls')
            if any((not c.get('ok')) or c.get('returned_model')!=PRIMARY_MODEL for c in r.get('app_calls',[])): errors.append(f'{kind}/{sid}: failed/wrong model call')
            if r.get('pcap_path') and not Path(r['pcap_path']).exists(): errors.append(f'{kind}/{sid}: pcap missing')
    by_sid={r['matched_to_scenario']:r for r in single}
    for r in mas:
        sid=r['scenario']['scenario_id']; sr=by_sid.get(sid)
        if not sr: continue
        if len(r.get('app_calls',[]))!=len(sr.get('app_calls',[])): errors.append(f'{sid}: call count mismatch')
        ratio=float(sr.get('matching',{}).get('prompt_byte_ratio') or 0)
        if not 0.70<=ratio<=1.30: errors.append(f'{sid}: prompt ratio {ratio}')
        if sr.get('system')!=system: errors.append(f'{sid}: single system mismatch')
    audit={'completed':not errors,'target':a.target,'system':system,'ticker':a.ticker,'scenario_ids':scenario_ids,'errors':errors,'probe':probe,
           'mas_actions':{r['scenario']['scenario_id']:r.get('action_label') for r in mas},
           'single_actions':{r['matched_to_scenario']:r.get('action_label') for r in single},
           'mas_calls':{r['scenario']['scenario_id']:len(r.get('app_calls',[])) for r in mas},
           'prompt_ratios':{r['matched_to_scenario']:r.get('matching',{}).get('prompt_byte_ratio') for r in single}}
    json_dump(a.output/'BATCH_VERIFICATION.json',audit)
    write_hash_manifest(a.output,a.output/'SHA256SUMS.txt')
    if errors: raise SystemExit('BATCH HARD VERIFICATION FAILED:\n'+'\n'.join(errors))
    (a.output/'BATCH_COMPLETE_SUCCESS.marker').write_text('verified\n',encoding='utf-8')
    print(json.dumps(audit,indent=2),flush=True)

if __name__=='__main__': main()
