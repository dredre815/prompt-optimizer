from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from openai import OpenAI

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.') )
OUT=ROOT/'worldseal_output'
OUT.mkdir(parents=True,exist_ok=True)
key=os.environ['DEEPSEEK_API_KEY']
client=OpenAI(api_key=key,base_url='https://api.deepseek.com',timeout=60,max_retries=3)
requested=['deepseek-v4-flash','deepseek-v4-pro']
probes=[]
for model in requested:
    started=time.time()
    resp=client.chat.completions.create(
        model=model,
        messages=[{'role':'system','content':'Return exactly JSON.'},{'role':'user','content':'Return {"ok":true,"requested":"'+model+'"} and nothing else.'}],
        temperature=0,
        response_format={'type':'json_object'},
        max_tokens=128,
    )
    content=resp.choices[0].message.content or ''
    obj=json.loads(content)
    probes.append({'requested_model':model,'returned_model':resp.model,'response':obj,'latency_s':time.time()-started,'usage':resp.usage.model_dump() if resp.usage else None})

repos={
 'TradingAgents':('TauricResearch/TradingAgents','a33fd4c0f134485a43553a2c23a63cb14adbd88f'),
 'swarm-trader':('zhound420/swarm-trader','3470b8291c438dc36b22ed37b7e56ba2bbf249b5'),
 'RD-Agent':('microsoft/RD-Agent','6762f84f9bc0f5c6486c50a00e128a57ac6c3683'),
}
repo_status={}
for name,(slug,sha) in repos.items():
    path=ROOT/'repos'/name
    got=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if got!=sha: raise RuntimeError(f'{name} commit mismatch {got} != {sha}')
    repo_status[name]={'slug':slug,'expected_commit':sha,'actual_commit':got}

sys.path.insert(0,str(ROOT/'repos'/'TradingAgents'))
from tradingagents.graph.trading_graph import TradingAgentsGraph
sys.path.insert(0,str(ROOT/'repos'/'swarm-trader'))
import risk_manager
sys.path.insert(0,str(ROOT/'repos'/'RD-Agent'))
from rdagent.core.proposal import Trace,HypothesisFeedback
from rdagent.scenarios.qlib.proposal.quant_proposal import QuantTrace,QlibQuantHypothesis

imports={
 'TradingAgentsGraph':f'{TradingAgentsGraph.__module__}.{TradingAgentsGraph.__name__}',
 'swarm_validate_trade':f'{risk_manager.validate_trade.__module__}.{risk_manager.validate_trade.__name__}',
 'RD_Trace':f'{Trace.__module__}.{Trace.__name__}',
 'RD_HypothesisFeedback':f'{HypothesisFeedback.__module__}.{HypothesisFeedback.__name__}',
 'RD_QuantTrace':f'{QuantTrace.__module__}.{QuantTrace.__name__}',
 'RD_QlibQuantHypothesis':f'{QlibQuantHypothesis.__module__}.{QlibQuantHypothesis.__name__}',
}
result={'completed':True,'api_probes':probes,'repositories':repo_status,'imports':imports,'python':sys.version}
(OUT/'SMOKE_SUCCESS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(OUT/'SMOKE_SUCCESS.marker').write_text('success\n',encoding='utf-8')
print(json.dumps(result,indent=2))
