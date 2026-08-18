import os,sys,json,random,tempfile,shutil,time,hashlib,math,sqlite3
from pathlib import Path
from collections import Counter,defaultdict
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
MODEL='deepseek-v4-flash';client=OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'],base_url='https://api.deepseek.com',timeout=90,max_retries=2)
SEED=20260819;random.seed(SEED);np.random.seed(SEED)
PAIR={0:'You are a risk-controlled swing trader. Preserve capital, keep positions modest, and prefer evidence that a move is durable. Use price, recent volume, and portfolio context together. Avoid overreacting to isolated observations; when evidence is incomplete, wait for confirmation rather than chase. Hold cash readily and avoid unnecessary turnover.',1:'You are a risk-controlled swing trader. Preserve capital and keep positions modest, but try to participate early when market behavior suggests new information is being incorporated. Use price, recent volume, and portfolio context together. A small exploratory position is acceptable before every signal is confirmed, followed by reassessment. Avoid oversized bets and unnecessary turnover.'}
MAGS=[1,2,5,10,20,40,80,160,320];ALL_Q=[-x for x in reversed(MAGS)]+MAGS;ACTIVE_Q=[-40,-20,-10,-5,-2,-1,1,2,5,10,20,40]
CAL_REPS=2;PASSIVE_SEQS_PER_SECRET=8;PASSIVE_SEQ_LEN=5;ACTIVE_TEST_REPS=10;MAX_ACTIVE_IMPACT=1.20
class Args:Daily_Price_Limit=0.7;Fluctuation_Constant=20.0;expense_ratio=0.03

def ds_request(prompt):
 last=''
 for k in range(3):
  try:
   r=client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],temperature=0.15,max_tokens=1024);last=r.choices[0].message.content or ''
   if last.strip():return last
  except Exception:time.sleep(1.2*(k+1))
 return last
gs.ChatGPT_request=ds_request;gs.GPT4_request=ds_request;gs.temp_sleep=lambda seconds=1:None

def empirical_passive_distribution():
 dbp=SM/'save'/'sim01'/'data.db';con=sqlite3.connect(str(dbp));cur=con.cursor()
 rows=cur.execute("SELECT type,quantity,stock_id,status FROM active_orders WHERE person_id>=0 AND quantity>0").fetchall();con.close()
 stock_float={0:1200.0,1:1000.0,2:1600.0}; mapped=[];statuses=Counter()
 for typ,qty,sid,status in rows:
  statuses[str(status)]+=1;scaled=max(1,int(round(float(qty)*1000.0/stock_float.get(int(sid),1000.0))));scaled=min(320,scaled);mag=min(MAGS,key=lambda x:abs(x-scaled));mapped.append(mag if str(typ).lower()=='buy' else -mag)
 if len(mapped)<10:raise RuntimeError(f'Published ATA sample has too few participant orders: {len(mapped)}')
 c=Counter(mapped);tot=sum(c.values());return mapped,{int(k):v/tot for k,v in sorted(c.items())},len(rows),dict(statuses)

def make_env(principle,q,root):
 root=Path(root);pp=root/'persona.json';sp=root/'stocks.json';pp.write_text(json.dumps([{'person_id':0,'name':'Victim','occupation':'Quantitative researcher','principle':principle,'investment_duration':'one year','daily_income_from_job':500,'cash':100000,'minimum_living_expense':60,'reflect_frequency':0},{'person_id':1,'name':'MarketParticipant','occupation':'Trader','principle':'benign background flow or bounded probe','investment_duration':'one year','daily_income_from_job':0,'cash':100000,'minimum_living_expense':0,'reflect_frequency':0}]),encoding='utf-8');sp.write_text(json.dumps([{'stock_id':0,'stock_name':'A','past_stock_last_prices':[100.0]*10,'quantity':1000,'DPS':0.0}]),encoding='utf-8')
 db=Database_operate(str(root/'data'));stock=Stock(0,db,str(sp));idx=Market_index([stock],db);broker=Broker([stock],db);v=Person(0,broker,[stock],db,str(pp));actor=Person(1,broker,[stock],db,str(pp));m=Market(broker,[v,actor,broker],[stock],db)
 endow=400;broker.inventories[0]-=endow;db.execute_sql(f"update account set quantity={broker.inventories[0]} where person_id=-1 and stock_id=0 and virtual_date=0");db.execute_sql(f"insert into account values(1,0,0,0,{endow},100.0,100.0,0,0)");actor.asset=endow*100.;actor.wealth=actor.cash+actor.asset;broker.ipo(0);v.add_gossip(0,'None');actor.add_gossip(0,'None');p0=float(stock.current_price)
 if q>0:actor.create_order(1,['buy','A',p0,int(q)],0,0)
 elif q<0:actor.create_order(1,['sell','A',p0,int(abs(q))],0,0)
 if q!=0:m.end_of_market(0,Args())
 idx.update_market_index(0);p1=float(stock.current_price);return db,stock,idx,v,p0,p1,abs(int(q))*((p0+p1)/2.)

def native_decide(v,stock,idx):
 try:
  ar,g=analysis(0,v,[stock],idx,1,0)
  if not ar:return 'INVALID','analysis_false'
  buy=run_gpt_prompt_choose_buy_stock(0,v,[stock],ar)
  if not buy:return 'INVALID','buy_false'
  name,qty,price=extract_for_choose_buy(buy)
  if name=='hold':return 'HOLD',str(buy)
  if name=='A':return 'BUY',str(buy)
  return 'INVALID',str(buy)
 except Exception as e:return 'INVALID',type(e).__name__+':'+str(e)[:120]
def trial(s,q,rep,phase):
 td=tempfile.mkdtemp(prefix='tl5b-')
 try:
  db,st,idx,v,p0,p1,notional=make_env(PAIR[s],q,td);a,raw=native_decide(v,st,idx);r={'phase':phase,'secret':s,'q':q,'rep':rep,'p0':p0,'p1':p1,'impact_pct':(p1/p0-1)*100,'probe_notional':notional,'action':a,'raw_digest':hashlib.sha256(raw.encode()).hexdigest()[:16]};db.close();return r
 finally:shutil.rmtree(td,ignore_errors=True)
def pbuy(rr):
 v=[x for x in rr if x['action'] in ('BUY','HOLD')];return .5 if not v else sum(x['action']=='BUY' for x in v)/len(v)
def sm(p,n=2):return (p*n+.5)/(n+1)
def js(p,q):
 e=1e-6;p=min(1-e,max(e,p));q=min(1-e,max(e,q));m=(p+q)/2
 def kl(a,b):return a*math.log(a/b)+(1-a)*math.log((1-a)/(1-b))
 return .5*kl(p,m)+.5*kl(q,m)
def upd(post,a,p0,p1):
 if a not in ('BUY','HOLD'):return post
 x=a=='BUY';likes=[p0 if x else 1-p0,p1 if x else 1-p1];z=post[0]*likes[0]+post[1]*likes[1];return post if z<=0 else [post[0]*likes[0]/z,post[1]*likes[1]/z]

def main(outdir):
 out=Path(outdir);out.mkdir(parents=True,exist_ok=True);rows=[];emp,dist,nraw,statuses=empirical_passive_distribution();cal={}
 for q in ALL_Q:
  by={};qr=[]
  for s in (0,1):
   rr=[trial(s,q,i,'cal') for i in range(CAL_REPS)];rows+=rr;qr+=rr;by[s]=rr
  p0,p1=pbuy(by[0]),pbuy(by[1]);impact=float(np.median([abs(r['impact_pct']) for r in qr]));notional=float(np.median([r['probe_notional'] for r in qr]));cal[q]={'p0':p0,'p1':p1,'impact':impact,'notional':notional,'score':js(p0,p1)/(1+notional/5000.)}
 aq=max(ACTIVE_Q,key=lambda q:cal[q]['score'] if cal[q]['impact']<=MAX_ACTIVE_IMPACT else -1)
 ac=[];aconf=[]
 for s in (0,1):
  for i in range(ACTIVE_TEST_REPS):
   r=trial(s,aq,i,'active_test');rows.append(r);p=upd([.5,.5],r['action'],sm(cal[aq]['p0']),sm(cal[aq]['p1']));ac.append(int(int(p[1]>p[0])==s));aconf.append(max(p))
 rng=random.Random(SEED+551);keys=list(dist);weights=[dist[k] for k in keys];byk=defaultdict(list);t90=[];seqs=[]
 for s in (0,1):
  for j in range(PASSIVE_SEQS_PER_SECRET):
   post=[.5,.5];steps=[];hit=None
   for k in range(1,PASSIVE_SEQ_LEN+1):
    q=rng.choices(keys,weights=weights,k=1)[0];r=trial(s,q,j*100+k,'passive_empirical');rows.append(r);post=upd(post,r['action'],sm(cal[q]['p0']),sm(cal[q]['p1']));pred=int(post[1]>post[0]);byk[k].append(int(pred==s));steps.append({'q':q,'action':r['action'],'confidence':max(post),'correct':int(pred==s)});hit=k if hit is None and max(post)>=.90 else hit
   t90.append(hit if hit is not None else PASSIVE_SEQ_LEN+1);seqs.append({'secret':s,'seq':j,'steps':steps})
 valid=sum(r['action']!='INVALID' for r in rows)/len(rows);pacc={k:float(np.mean(v)) for k,v in byk.items()};aa=float(np.mean(ac));mt=float(np.median(t90));support=bool(aa-pacc[1]>=.15 and mt>1 and valid>=.90)
 summary={'model':MODEL,'seed':SEED,'native_ata_prompts':True,'passive_source':'pinned ATA save/sim01/data.db participant orders','raw_sample_orders':nraw,'sample_status_counts':statuses,'mapped_passive_events':len(emp),'passive_q_distribution':dist,'calibration':cal,'active_q':aq,'active_one_query_accuracy':aa,'active_median_confidence':float(np.median(aconf)),'passive_accuracy_by_observations':pacc,'passive_median_events_to_90pct':mt,'valid_response_rate':valid,'active_story_supported':support,'decision_rule':'active one-query - passive one-event >=0.15 AND passive median events-to-90% >1 AND valid>=0.90'}
 json.dump(summary,open(out/'summary.json','w'),indent=2);json.dump(seqs,open(out/'passive_sequences.json','w'),indent=2)
 with open(out/'trials.jsonl','w') as f:
  for r in rows:f.write(json.dumps(r)+'\n')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main(os.environ.get('TRADELEAK_STAGE5_OUT','tradeleak_stage5_output'))
