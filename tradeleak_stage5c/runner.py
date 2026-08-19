import os,sys,json,random,tempfile,shutil,time,hashlib,math
from pathlib import Path
from collections import defaultdict
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
PAIR={0:'You are a risk-controlled swing trader. Preserve capital, keep positions modest, and prefer evidence that a move is durable. Use price, recent volume, and portfolio context together. Avoid overreacting to isolated observations; when evidence is incomplete, wait for confirmation rather than chase. Hold cash readily and avoid unnecessary turnover.',1:'You are a risk-controlled swing trader. Preserve capital and keep positions modest, but try to participate early when market behavior suggests new information is being incorporated. Use price, recent volume, and portfolio context together. A small exploratory position is acceptable before every signal is confirmed, followed by reassessment. Avoid oversized bets and unnecessary turnover.'}
CAL_REPS=2; TEST_REPS=2

def ds_request(prompt):
 last=''
 for k in range(3):
  try:
   r=client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],temperature=0.15,max_tokens=1024); last=r.choices[0].message.content or ''
   if last.strip(): return last
  except Exception: time.sleep(1.2*(k+1))
 return last
gs.ChatGPT_request=ds_request; gs.GPT4_request=ds_request; gs.temp_sleep=lambda seconds=1:None

def published_windows():
 src=json.load(open(SM/'save'/'sim01'/'stocks.json'))
 out=[]
 for s in src:
  ps=[float(x) for x in s['past_stock_last_prices']]
  for i in range(4,len(ps)):
   w=ps[i-4:i+1]
   out.append({'source_stock':s['stock_name'],'end_index':i,'prices':w,'last_step_return_pct':(w[-1]/w[-2]-1)*100,'window_return_pct':(w[-1]/w[0]-1)*100})
 return out

def make_env(principle,prices,root):
 root=Path(root);pp=root/'persona.json';sp=root/'stocks.json'
 pp.write_text(json.dumps([{'person_id':0,'name':'Victim','occupation':'Quantitative researcher','principle':principle,'investment_duration':'one year','daily_income_from_job':500,'cash':100000,'minimum_living_expense':60,'reflect_frequency':0}]),encoding='utf-8')
 sp.write_text(json.dumps([{'stock_id':0,'stock_name':'A','past_stock_last_prices':prices,'quantity':1000,'DPS':0.0}]),encoding='utf-8')
 db=Database_operate(str(root/'data')); st=Stock(0,db,str(sp)); idx=Market_index([st],db); br=Broker([st],db); v=Person(0,br,[st],db,str(pp)); m=Market(br,[v,br],[st],db); br.ipo(0);v.add_gossip(0,'None');idx.update_market_index(0); return db,st,idx,v

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

def trial(s,w,rep,phase,wid):
 td=tempfile.mkdtemp(prefix='tl5c-')
 try:
  db,st,idx,v=make_env(PAIR[s],w['prices'],td);a,raw=native_decide(v,st,idx);r={'phase':phase,'window_id':wid,'source_stock':w['source_stock'],'end_index':w['end_index'],'prices':w['prices'],'last_step_return_pct':w['last_step_return_pct'],'window_return_pct':w['window_return_pct'],'secret':s,'rep':rep,'action':a,'raw_digest':hashlib.sha256(raw.encode()).hexdigest()[:16]};db.close();return r
 finally:shutil.rmtree(td,ignore_errors=True)

def pbuy(rr):
 v=[x for x in rr if x['action'] in ('BUY','HOLD')]; return .5 if not v else sum(x['action']=='BUY' for x in v)/len(v)
def smooth(p,n=2):return (p*n+.5)/(n+1)
def predict(a,p0,p1):
 if a not in ('BUY','HOLD'):return None
 x=a=='BUY'; l0=p0 if x else 1-p0; l1=p1 if x else 1-p1
 return 0 if l0>=l1 else 1

def main(outdir):
 out=Path(outdir);out.mkdir(parents=True,exist_ok=True);wins=published_windows();rows=[];cal={};diag=[];correct=[];perwin={}
 for wid,w in enumerate(wins):
  by={}
  for s in (0,1):
   rr=[trial(s,w,i,'cal',wid) for i in range(CAL_REPS)];rows+=rr;by[s]=rr
  p0,p1=pbuy(by[0]),pbuy(by[1]);cal[wid]=(smooth(p0),smooth(p1));gap=abs(p0-p1);diag.append(gap>=.5)
  perwin[wid]={'source_stock':w['source_stock'],'end_index':w['end_index'],'last_step_return_pct':w['last_step_return_pct'],'window_return_pct':w['window_return_pct'],'p_buy_s0_cal':p0,'p_buy_s1_cal':p1,'cal_gap':gap}
 for wid,w in enumerate(wins):
  p0,p1=cal[wid];wc=[]
  for s in (0,1):
   for i in range(TEST_REPS):
    r=trial(s,w,i,'test',wid);rows.append(r);pr=predict(r['action'],p0,p1);z=int(pr==s);correct.append(z);wc.append(z)
  perwin[wid]['heldout_accuracy']=float(np.mean(wc))
 valid=sum(r['action']!='INVALID' for r in rows)/len(rows);df=float(np.mean(diag));acc=float(np.mean(correct));wait=(1/df if df>0 else None)
 # Stage-4 active q=20 benchmark is frozen, not re-estimated here.
 active_ref={'q':20,'accuracy':1.0,'impact_pct':0.7142857142857117,'probe_cost':2014.2857142857101}
 summary={'model':MODEL,'seed':SEED,'native_ata_prompts':True,'passive_source':'18 rolling 5-day windows from pinned ATA save/sim01/stocks.json','num_windows':len(wins),'cal_reps':CAL_REPS,'test_reps':TEST_REPS,'valid_response_rate':valid,'passive_diagnostic_fraction':df,'passive_expected_windows_to_diagnostic':wait,'passive_heldout_accuracy':acc,'active_stage4_reference':active_ref,'per_window':perwin}
 json.dump(summary,open(out/'summary.json','w'),indent=2)
 with open(out/'trials.jsonl','w') as f:
  for r in rows:f.write(json.dumps(r)+'\n')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main(os.environ.get('TRADELEAK_STAGE5C_OUT','tradeleak_stage5c_output'))
