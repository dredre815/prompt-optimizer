import os,sys,json,random,tempfile,shutil,time,hashlib,itertools
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

MODEL='deepseek-v4-flash'; SEED=20260819; random.seed(SEED); np.random.seed(SEED)
client=OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'],base_url='https://api.deepseek.com',timeout=90,max_retries=2)
REPS=6
PAIR={
0:'You are a risk-controlled intraday swing trader. Preserve capital and keep positions modest. When a market shows a wide intraday range, repeated reversals, or an unstable path without new fundamental information, treat that as uncertainty rather than confirmation. Prefer waiting for a cleaner close and a more stable trading range before adding exposure. Avoid unnecessary turnover.',
1:'You are a risk-controlled range-expansion trader. Preserve capital and keep positions modest. When a market absorbs a wide intraday range and still finishes above its earlier reference, that range expansion can indicate active information discovery even before longer confirmation develops. A small exploratory position is acceptable, followed by reassessment. Avoid oversized bets and unnecessary turnover.'}

class Args:
    Daily_Price_Limit=0.7
    Fluctuation_Constant=20.0
    expense_ratio=0.03

def ds_request(prompt):
    last=''
    for k in range(3):
        try:
            r=client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],temperature=0.15,max_tokens=1024)
            last=r.choices[0].message.content or ''
            if last.strip(): return last
        except Exception: time.sleep(1.2*(k+1))
    return last

gs.ChatGPT_request=ds_request; gs.GPT4_request=ds_request; gs.temp_sleep=lambda seconds=1:None

def make_base(principle,root):
    root=Path(root); pp=root/'persona.json'; sp=root/'stocks.json'
    pp.write_text(json.dumps([
        {'person_id':0,'name':'Victim','occupation':'Quantitative researcher','principle':principle,'investment_duration':'one year','daily_income_from_job':500,'cash':100000,'minimum_living_expense':60,'reflect_frequency':0},
        {'person_id':1,'name':'MarketParticipant','occupation':'Trader','principle':'bounded closed-market participant','investment_duration':'one year','daily_income_from_job':0,'cash':100000,'minimum_living_expense':0,'reflect_frequency':0}
    ]),encoding='utf-8')
    sp.write_text(json.dumps([{'stock_id':0,'stock_name':'A','past_stock_last_prices':[100.0]*10,'quantity':1000,'DPS':0.0}]),encoding='utf-8')
    db=Database_operate(str(root/'data')); st=Stock(0,db,str(sp)); idx=Market_index([st],db); br=Broker([st],db); v=Person(0,br,[st],db,str(pp)); actor=Person(1,br,[st],db,str(pp)); m=Market(br,[v,actor,br],[st],db)
    endow=500; br.inventories[0]-=endow; db.execute_sql(f"update account set quantity={br.inventories[0]} where person_id=-1 and stock_id=0 and virtual_date=0")
    db.execute_sql(f"insert into account values(1,0,0,0,{endow},100.0,100.0,0,0)"); actor.asset=endow*100.; actor.wealth=actor.cash+actor.asset
    br.ipo(0); v.add_gossip(0,'None'); actor.add_gossip(0,'None'); idx.update_market_index(0)
    return db,st,idx,br,v,actor,m

def apply_sequence(seq,principle='temporary policy for geometry search'):
    td=tempfile.mkdtemp(prefix='tl6b-geom-')
    try:
        db,st,idx,br,v,a,m=make_base(principle,td); prices=[float(st.current_price)]
        for side,q in seq:
            p=float(st.current_price)
            if side=='buy': a.create_order(1,['buy','A',p,int(q)],0,0)
            else: a.create_order(1,['sell','A',p,int(q)],0,0)
            m.end_of_market(0,Args()); prices.append(float(st.current_price))
        idx.update_market_index(0); obs=st.query_prompt_values(0); db.close()
        return {'seq':seq,'prices':prices,'final':prices[-1],'ret_pct':(prices[-1]/prices[0]-1)*100,'high':max(prices),'low':min(prices),'range_pct':(max(prices)-min(prices))/prices[0]*100,'obs':obs}
    finally: shutil.rmtree(td,ignore_errors=True)

def choose_matched_states():
    quiet=[]; volatile=[]
    for q in [5,10,20,40,80]:
        s=apply_sequence([('buy',q)])
        if 0.15 <= s['ret_pct'] <= 2.0: quiet.append(s)
    mags=[20,40,80,120,160,240]
    for q1,q2 in itertools.product(mags,mags):
        for seq in [[('buy',q1),('sell',q2)],[('sell',q1),('buy',q2)]]:
            s=apply_sequence(seq)
            if 0.15 <= s['ret_pct'] <= 2.0: volatile.append(s)
    candidates=[]
    for q,v in itertools.product(quiet,volatile):
        mismatch=abs(q['final']/v['final']-1)*100; rg=v['range_pct']-q['range_pct']
        if mismatch<=0.15 and rg>=0.75: candidates.append((mismatch,-rg,q,v))
    if not candidates:
        for q,v in itertools.product(quiet,volatile):
            mismatch=abs(q['final']/v['final']-1)*100; rg=v['range_pct']-q['range_pct']
            if mismatch<=0.25 and rg>=0.5: candidates.append((mismatch,-rg,q,v))
    if not candidates: raise RuntimeError('No price-matched low/high-range state pair found under frozen ATA action library')
    candidates.sort(key=lambda x:(x[0],x[1])); _,_,q,v=candidates[0]
    return q,v

def make_state(principle,seq,root):
    db,st,idx,br,v,a,m=make_base(principle,root); prices=[float(st.current_price)]
    for side,q in seq:
        p=float(st.current_price)
        if side=='buy': a.create_order(1,['buy','A',p,int(q)],0,0)
        else: a.create_order(1,['sell','A',p,int(q)],0,0)
        m.end_of_market(0,Args()); prices.append(float(st.current_price))
    idx.update_market_index(0); return db,st,idx,v,prices,st.query_prompt_values(0)

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

def trial(secret,label,seq,rep):
    td=tempfile.mkdtemp(prefix='tl6b-')
    try:
        db,st,idx,v,prices,obs=make_state(PAIR[secret],seq,td); a,raw=native_decide(v,st,idx)
        r={'secret':secret,'condition':label,'rep':rep,'seq':seq,'path':prices,'final':prices[-1],'ret_pct':(prices[-1]/prices[0]-1)*100,'range_pct':(max(prices)-min(prices))/prices[0]*100,'prompt_values':obs,'action':a,'raw_digest':hashlib.sha256(raw.encode()).hexdigest()[:16]}; db.close(); return r
    finally: shutil.rmtree(td,ignore_errors=True)

def pbuy(rows):
    v=[r for r in rows if r['action'] in ('BUY','HOLD')]
    return .5 if not v else sum(r['action']=='BUY' for r in v)/len(v)

def main(outdir):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True);low,high=choose_matched_states(); rows=[]; metrics={}
    states={'flat':[],'low_range':low['seq'],'high_range':high['seq']}
    for label,seq in states.items():
        by={}
        for s in (0,1):
            rr=[trial(s,label,seq,i) for i in range(REPS)]; rows+=rr; by[s]=rr
        p0,p1=pbuy(by[0]),pbuy(by[1]); metrics[label]={'p_buy_s0':p0,'p_buy_s1':p1,'buy_gap':abs(p0-p1),'median_final':float(np.median([r['final'] for r in by[0]+by[1]])),'median_ret_pct':float(np.median([r['ret_pct'] for r in by[0]+by[1]])),'median_range_pct':float(np.median([r['range_pct'] for r in by[0]+by[1]]))}
    valid=sum(r['action']!='INVALID' for r in rows)/len(rows); mismatch=abs(low['final']/high['final']-1)*100; range_gain=high['range_pct']-low['range_pct']; activation=metrics['high_range']['buy_gap']-metrics['low_range']['buy_gap']
    success=bool(mismatch<=0.15 and range_gain>=0.75 and metrics['low_range']['buy_gap']<=0.25 and metrics['high_range']['buy_gap']>=0.5 and activation>=0.5 and valid>=0.95)
    summary={'experiment':'Stage-6B intraday-path activation','model':MODEL,'seed':SEED,'native_ata_prompts':True,'visible_modality':'ATA-native closing-price history + current price change + intraday high/low/mean','secret':'intraday range interpreted as uncertainty vs information-discovery signal','sequence_selection':'market-geometry only; no LLM outputs used','low_range_geometry':low,'high_range_geometry':high,'final_close_mismatch_pct':mismatch,'range_gain_pct':range_gain,'reps_per_secret_condition':REPS,'valid_response_rate':valid,'condition_metrics':metrics,'activation_gain':activation,'activation_supported':success}
    json.dump(summary,open(out/'summary.json','w'),indent=2)
    with open(out/'trials.jsonl','w') as f:
        for r in rows:f.write(json.dumps(r)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main(os.environ.get('TRADELEAK_STAGE6B_OUT','tradeleak_stage6b_output'))
