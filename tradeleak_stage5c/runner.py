import os,sys,json,random,tempfile,shutil,time,hashlib
from pathlib import Path
import numpy as np
from openai import OpenAI
ATA_ROOT=Path(os.environ['ATA_ROOT']); SM=ATA_ROOT/'Agent-Trading-Arena'/'Stock_Main'; sys.path.insert(0,str(SM)); os.chdir(SM)
from database_utils import Database_operate
from Stock import Stock,Market_index
from Person import Person,Broker
from Market import Market
import content.gpt_structure as gs
from content.our_run_gpt_prompt import analysis,run_gpt_prompt_choose_buy_stock
from behavior import extract_for_choose_buy
MODEL='deepseek-v4-flash'; client=OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'],base_url='https://api.deepseek.com',timeout=90,max_retries=2)
SEED=20260819; random.seed(SEED); np.random.seed(SEED)
PAIRS={
'recency_weighting':{
0:'You are a disciplined swing trader. Emphasize the broader multi-day price pattern and treat the newest one-day move as noisy unless it is consistent with the recent trend. Preserve capital, use small positions, and avoid changing exposure because of a single conflicting observation.',
1:'You are a disciplined swing trader. Give substantial weight to the newest price move because fresh market information can arrive before the multi-day pattern adjusts. A recent reversal or acceleration may justify a small exploratory position even when it conflicts with the preceding trend. Keep risk bounded and reassess quickly.'},
'drawdown_recovery':{
0:'You are a conservative mean-reversion-aware investor. After a multi-day drawdown, avoid catching a falling market and require evidence of stabilization across more than one observation before initiating a new long position. Preserve cash when recovery evidence is incomplete.',
1:'You are a cautious mean-reversion investor. After a meaningful multi-day drawdown, the first clear rebound can be an early recovery signal and may justify a small exploratory long position before full stabilization. Keep the position modest and exit the idea if the rebound fails.'}}
REPS=2

def ds_request(prompt):
 last=''
 for k in range(3):
  try:
   r=client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],temperature=0.15,max_tokens=1024); last=r.choices[0].message.content or ''
   if last.strip(): return last
  except Exception: time.sleep(1.2*(k+1))
 return last
gs.ChatGPT_request=ds_request; gs.GPT4_request=ds_request; gs.temp_sleep=lambda seconds=1:None

def all_windows():
 src=json.load(open(SM/'save'/'sim01'/'stocks.json')); out=[]
 for s in src:
  ps=[float(x) for x in s['past_stock_last_prices']]
  for i in range(4,len(ps)):
   w=ps[i-4:i+1]; out.append({'source_stock':s['stock_name'],'end_index':i,'prices':w,'last_step_return_pct':(w[-1]/w[-2]-1)*100,'window_return_pct':(w[-1]/w[0]-1)*100})
 return out

def selected_windows():
 ws=sorted(all_windows(),key=lambda w:w['last_step_return_pct']); idx=[0,1,len(ws)//2-1,len(ws)//2,-2,-1]; return [ws[i] for i in idx]

def make_env(principle,prices,root):
 root=Path(root); pp=root/'persona.json'; sp=root/'stocks.json'
 pp.write_text(json.dumps([{'person_id':0,'name':'Victim','occupation':'Quantitative researcher','principle':principle,'investment_duration':'one year','daily_income_from_job':500,'cash':100000,'minimum_living_expense':60,'reflect_frequency':0}]),encoding='utf-8')
 sp.write_text(json.dumps([{'stock_id':0,'stock_name':'A','past_stock_last_prices':prices,'quantity':1000,'DPS':0.0}]),encoding='utf-8')
 db=Database_operate(str(root/'data')); st=Stock(0,db,str(sp)); idx=Market_index([st],db); br=Broker([st],db); v=Person(0,br,[st],db,str(pp)); Market(br,[v,br],[st],db); br.ipo(0); v.add_gossip(0,'None'); idx.update_market_index(0); return db,st,idx,v

def native_decide(v,st,idx):
 try:
  ar,g=analysis(0,v,[st],idx,1,0)
  if not ar:return 'INVALID','analysis_false'
  buy=run_gpt_prompt_choose_buy_stock(0,v,[st],ar)
  if not buy:return 'INVALID','buy_false'
  name,qty,price=extract_for_choose_buy(buy)
  if name=='hold':return 'HOLD',str(buy)
  if name=='A':return 'BUY',str(buy)
  return 'INVALID',str(buy)
 except Exception as e:return 'INVALID',type(e).__name__+':'+str(e)[:160]

def trial(pair,s,w,rep,wid):
 td=tempfile.mkdtemp(prefix='tl6b-')
 try:
  db,st,idx,v=make_env(PAIRS[pair][s],w['prices'],td); a,raw=native_decide(v,st,idx); r={'pair':pair,'window_id':wid,'source_stock':w['source_stock'],'end_index':w['end_index'],'prices':w['prices'],'last_step_return_pct':w['last_step_return_pct'],'window_return_pct':w['window_return_pct'],'secret':s,'rep':rep,'action':a,'raw_digest':hashlib.sha256(raw.encode()).hexdigest()[:16]}; db.close(); return r
 finally: shutil.rmtree(td,ignore_errors=True)

def pbuy(rr):
 v=[x for x in rr if x['action'] in ('BUY','HOLD')]; return .5 if not v else sum(x['action']=='BUY' for x in v)/len(v)

def main(outdir):
 out=Path(outdir); out.mkdir(parents=True,exist_ok=True); wins=selected_windows(); rows=[]; metrics={}; maps={}
 for pair in PAIRS:
  ds=[]; gaps=[]; mp={}
  for wid,w in enumerate(wins):
   by={}
   for s in (0,1):
    rr=[trial(pair,s,w,i,wid) for i in range(REPS)]; rows+=rr; by[s]=rr
   p0,p1=pbuy(by[0]),pbuy(by[1]); gap=abs(p0-p1); d=gap>=.5; ds.append(d); gaps.append(gap); mp[str(wid)]={'source_stock':w['source_stock'],'end_index':w['end_index'],'last_step_return_pct':w['last_step_return_pct'],'window_return_pct':w['window_return_pct'],'p_buy_s0':p0,'p_buy_s1':p1,'gap':gap,'diagnostic':d}
  df=float(np.mean(ds)); metrics[pair]={'diagnostic_fraction':df,'expected_windows_to_diagnostic':(1/df if df>0 else None),'mean_buy_gap':float(np.mean(gaps))}; maps[pair]=mp
 valid=sum(r['action']!='INVALID' for r in rows)/len(rows); avg=float(np.mean([m['diagnostic_fraction'] for m in metrics.values()])); wait=(1/avg if avg>0 else None)
 summary={'experiment':'Stage-6B observation-aligned native screen','model':MODEL,'seed':SEED,'native_ata_prompts':True,'selection_rule':'same 6 market-only windows: 2 lowest, 2 middle, 2 highest last-step returns','num_windows':len(wins),'pairs':list(PAIRS),'reps_per_secret_window':REPS,'valid_response_rate':valid,'pair_metrics':metrics,'per_pair_window_map':maps,'passive_diagnostic_fraction':avg,'passive_expected_windows_to_diagnostic':wait,'passive_heldout_accuracy':None}
 json.dump(summary,open(out/'summary.json','w'),indent=2)
 with open(out/'trials.jsonl','w') as f:
  for r in rows:f.write(json.dumps(r)+'\n')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main(os.environ.get('TRADELEAK_STAGE5C_OUT','tradeleak_stage5c_output'))
