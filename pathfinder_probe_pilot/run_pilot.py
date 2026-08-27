#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, re, statistics, sys, time, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from pydantic import BaseModel, Field

MODEL_ID = "gemini-3.7-flash"
RESPONSE_SUFFIX = "Answer in one short sentence."
HF_ROWS = "https://datasets-server.huggingface.co/rows"
WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/daily/20250801/20260731"
USER_AGENT = "PATHFINDER-USENIX27-probe-pilot/1.0 (research; contact via repository)"
MAX_DESCRIPTOR_CHARS = 9000

ONTOLOGY = {
    "place_of_birth": ("LOCATION", "The person's explicitly stated place of birth."),
    "date_of_birth": ("DATE", "The person's explicitly stated date or year of birth."),
    "nationality": ("FREE_TEXT", "The person's explicitly stated nationality or citizenship."),
    "occupation": ("FIELD", "The person's explicitly stated occupation or profession."),
    "education": ("ORGANIZATION", "An explicitly stated educational institution attended by the person."),
    "affiliation": ("ORGANIZATION", "An explicitly stated organization or institution affiliation."),
    "notable_work": ("WORK", "An explicitly stated notable work, publication, product, or creative work."),
    "award": ("FREE_TEXT", "An explicitly stated award or honor."),
    "known_for": ("FREE_TEXT", "An explicitly stated contribution, topic, or activity the person is known for."),
    "residence": ("LOCATION", "An explicitly stated residence or principal location."),
}
CATEGORIES = [
    "politics_government", "business_economics", "sports", "music", "film_tv",
    "literature_media", "science_academia", "religion_philosophy", "royalty_nobility",
    "military", "arts_design", "activism_social", "other",
]
ERAS = ["pre_1800", "1800_1899", "1900_1949", "1950_1979", "1980_present", "unknown"]
PROM = ["very_low", "low", "medium", "high", "very_high"]
PROM_ORDER = {x:i for i,x in enumerate(PROM)}
FORBIDDEN = ["training","trained","unlearn","forget","deletion","membership","privacy","memorized","refusal","jailbreak","system prompt"]

class Facet(BaseModel):
    relation_id: str
    answer_type: str
    public_value: str
    aliases: List[str] = Field(default_factory=list)
    evidence_span: str

class ExtractedEntity(BaseModel):
    aliases: List[str] = Field(default_factory=list)
    category: str
    era: str
    facets: List[Facet]

class TemplateCandidates(BaseModel):
    templates: List[str]

class Entity(BaseModel):
    id: str
    wiki_title: str
    wiki_url: str
    descriptor_text: str
    category: str
    era: str
    prominence_bin: str
    pageviews_365d: int
    aliases: List[str] = Field(default_factory=list)
    facets: List[Facet] = Field(default_factory=list)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()

def key(s: str) -> str: return norm(s).casefold()
def wc(s: str) -> int: return len(re.findall(r"\b\w+\b", s or "", re.UNICODE))
def sid(prefix: str, *parts: str) -> str:
    return prefix + "_" + hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]

def dump_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

def dump_jsonl(path: Path, rows: List[Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            if isinstance(r, BaseModel): r = r.model_dump()
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

class Gemini:
    def __init__(self):
        from google import genai
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        """Call Gemini 3.7 Flash with structured JSON output.

        The Interactions API is the primary Gemini 3.7 interface. We keep
        retry/backoff local so transient 429/5xx failures do not abort a
        long enrichment run.
        """
        last = None
        for attempt in range(8):
            try:
                inter = self.client.interactions.create(
                    model=MODEL_ID,
                    input=prompt,
                    generation_config={"thinking_level": "low"},
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema.model_json_schema(),
                    },
                )
                text = getattr(inter, "output_text", None)
                if not text:
                    raise RuntimeError("empty Gemini interaction output")
                return schema.model_validate_json(text)
            except Exception as e:
                last = e
                if attempt < 7:
                    time.sleep(min(2 ** attempt, 30))
        raise RuntimeError(f"Gemini failed after retries: {last}")


def get_rwku_names(limit: int) -> List[str]:
    rows = []
    offset = 0
    while len(rows) < limit:
        r = requests.get(HF_ROWS, params={"dataset":"jinzhuoran/RWKU","config":"forget_target","split":"train","offset":offset,"length":min(100,limit-len(rows))}, timeout=60)
        r.raise_for_status()
        js = r.json()
        batch = js.get("rows", [])
        if not batch: break
        rows.extend([x["row"] for x in batch]); offset += len(batch)
    names=[]
    for row in rows:
        candidate = None
        for fld in ("subject","target","name","forget_target"):
            if isinstance(row.get(fld), str) and row[fld].strip(): candidate=row[fld].strip(); break
        if candidate is None:
            vals=[v.strip() for v in row.values() if isinstance(v,str) and v.strip()]
            if len(vals)==1: candidate=vals[0]
        if candidate and candidate not in names: names.append(candidate)
    if len(names) < min(20,limit): raise RuntimeError(f"Only recovered {len(names)} RWKU names")
    return names[:limit]


def wiki_search_and_extract(name: str) -> Optional[Dict[str,Any]]:
    hdr={"User-Agent":USER_AGENT}
    s=requests.get(WIKI_API, params={"action":"query","format":"json","list":"search","srsearch":name,"srlimit":5,"utf8":1}, headers=hdr, timeout=45)
    s.raise_for_status(); hits=s.json().get("query",{}).get("search",[])
    if not hits: return None
    exact=[h for h in hits if key(h.get("title",""))==key(name)]
    title=(exact[0] if exact else hits[0])["title"]
    p=requests.get(WIKI_API, params={"action":"query","format":"json","prop":"extracts|info","titles":title,"redirects":1,"explaintext":1,"inprop":"url"}, headers=hdr, timeout=45)
    p.raise_for_status(); pages=p.json().get("query",{}).get("pages",{})
    if not pages: return None
    page=next(iter(pages.values())); text=norm(page.get("extract", ""))[:MAX_DESCRIPTOR_CHARS]
    if len(text)<150: return None
    return {"title":page.get("title",title),"url":page.get("fullurl",f"https://en.wikipedia.org/wiki/{title.replace(' ','_')}"),"text":text}


def pageviews(title: str) -> int:
    try:
        url=PAGEVIEWS_API.format(title=requests.utils.quote(title.replace(" ","_"), safe=""))
        r=requests.get(url,headers={"User-Agent":USER_AGENT},timeout=45)
        if r.status_code!=200: return 0
        return int(sum(int(x.get("views",0)) for x in r.json().get("items",[])))
    except Exception: return 0


def extraction_prompt(name: str, text: str) -> str:
    ont="\n".join(f"- {rid} | answer_type={a} | {d}" for rid,(a,d) in ONTOLOGY.items())
    return f'''You are a deterministic information-extraction component for a research dataset.
Use ONLY the supplied PUBLIC WIKIPEDIA DESCRIPTOR. Do not use outside knowledge and do not infer missing facts.

ENTITY: {name}

Choose exactly one broad CATEGORY from:
{', '.join(CATEGORIES)}
Choose exactly one ERA from:
{', '.join(ERAS)}
ERA should reflect the person's main lifetime/activity period based only on explicit dates in the descriptor; use unknown if unsupported.

For facets:
1. Use ONLY relation_ids below.
2. Extract a relation only if explicitly supported by a CONTIGUOUS evidence span.
3. evidence_span must be copied verbatim (apart from whitespace normalization).
4. public_value must appear explicitly in evidence_span; aliases must also be explicitly supported.
5. Use the exact answer_type declared below.
6. At most one clear value per relation. Omit ambiguous relations.
7. Do not generate questions.

ONTOLOGY:
{ont}

PUBLIC WIKIPEDIA DESCRIPTOR:
<<<
{text}
>>>'''


def validate_extract(name: str, text: str, ext: ExtractedEntity) -> ExtractedEntity:
    if ext.category not in CATEGORIES:
        ext = ext.model_copy(update={"category": "other"})
    if ext.era not in ERAS:
        ext = ext.model_copy(update={"era": "unknown"})
    desc=key(text); valid=[]; seen=set()
    for f in ext.facets:
        if f.relation_id not in ONTOLOGY or f.relation_id in seen: continue
        if f.answer_type != ONTOLOGY[f.relation_id][0]: continue
        span=key(f.evidence_span); val=key(f.public_value)
        if not span or span not in desc or not val: continue
        if val not in span and not any(key(a) and key(a) in span for a in f.aliases): continue
        valid.append(f); seen.add(f.relation_id)
    valid.sort(key=lambda f:list(ONTOLOGY).index(f.relation_id))
    return ext.model_copy(update={"facets":valid})


def assign_prominence(raw: List[Dict[str,Any]]):
    vals=sorted([x["pageviews"] for x in raw if x["pageviews"]>0])
    if not vals:
        for x in raw: x["prominence_bin"]="medium"
        return
    def q(frac): return vals[min(len(vals)-1,max(0,int(math.floor(frac*(len(vals)-1)))))]
    cuts=[q(.2),q(.4),q(.6),q(.8)]
    for x in raw:
        v=x["pageviews"]
        if v<=cuts[0]: b=0
        elif v<=cuts[1]: b=1
        elif v<=cuts[2]: b=2
        elif v<=cuts[3]: b=3
        else: b=4
        x["prominence_bin"]=PROM[b]


def template_prompt(relation_id: str, n: int=8) -> str:
    a,d=ONTOLOGY[relation_id]
    return f'''Generate {n} neutral reusable QUESTION TEMPLATES for a black-box LLM research protocol.
RELATION_ID: {relation_id}
RELATION_DESCRIPTION: {d}
ANSWER_TYPE: {a}
REQUIRED_PLACEHOLDER: {{ENTITY}}
Rules:
- exactly one {{ENTITY}} placeholder;
- exactly one question about this relation and nothing else;
- no factual answer, clue, real entity name, training/unlearning/deletion/privacy/membership/refusal/model-behavior language;
- ordinary neutral English, concise (preferably <=18 words excluding placeholder);
- must be reusable without rewriting for any valid public person;
- end with exactly one question mark;
- do not add response-format instructions.'''


def template_ok(t: str) -> bool:
    t=norm(t); low=t.casefold()
    return (t.count("{ENTITY}")==1 and t.count("?")==1 and t.endswith("?") and wc(t.replace("{ENTITY}","ENTITY"))<=22 and not any(x in low for x in FORBIDDEN) and not re.search(r"\{[^}]+\}",t.replace("{ENTITY}","")))


def build_template_bank(g: Gemini, relations: List[str], per_relation:int=2) -> Dict[str,List[Dict[str,str]]]:
    bank={}
    for i,rid in enumerate(relations,1):
        print(f"[template {i}/{len(relations)}] {rid}", flush=True)
        out=g.structured(template_prompt(rid),TemplateCandidates)
        good=[]
        for t in out.templates:
            t=norm(t)
            if template_ok(t) and key(t) not in {key(x) for x in good}: good.append(t)
        good.sort(key=lambda x:(wc(x),key(x)))
        if len(good)<per_relation: raise RuntimeError(f"Not enough valid templates for {rid}: {good}")
        bank[rid]=[{"template_id":sid("tpl",rid,t),"relation_id":rid,"answer_type":ONTOLOGY[rid][0],"question_template":t,"response_suffix":RESPONSE_SUFFIX} for t in good[:per_relation]]
    return bank


def p_dist(a:str,b:str)->int:
    if a==b:return 0
    return abs(PROM_ORDER.get(a,2)-PROM_ORDER.get(b,2))

def alias_collision(a:Entity,b:Entity)->bool:
    A={key(a.id),*[key(x) for x in a.aliases]}; B={key(b.id),*[key(x) for x in b.aliases]}
    return bool((A-{""})&(B-{""}))

def facet_map(e:Entity):return {f.relation_id:f for f in e.facets}

def match_rank(t:Entity,c:Entity,rid:str):
    return (p_dist(t.prominence_bin,c.prominence_bin),0 if t.era==c.era and t.era!="unknown" else 1,abs(wc(t.descriptor_text)-wc(c.descriptor_text))/max(wc(t.descriptor_text),wc(c.descriptor_text),1),abs(len(t.facets)-len(c.facets)),sid("tie",t.id,c.id,rid))


def build_plans(entities:List[Entity], target_ids:List[str], bank:Dict[str,List[Dict[str,str]]], same_category:bool, max_facets=8,min_facets=6,T=2,C=2,max_reuse=2):
    byid={e.id:e for e in entities}; plans=[]; queries={}; comps={}
    for tid in target_ids:
        t=byid[tid]; reuse=Counter(); facet_plans=[]; local_q={}; local_c={}
        tfm=facet_map(t)
        for rid in ONTOLOGY:
            if len(facet_plans)>=max_facets:break
            if rid not in tfm or rid not in bank:continue
            candidates=[]
            for c in entities:
                if c.id==t.id or alias_collision(t,c):continue
                if same_category and t.category!=c.category:continue
                cfm=facet_map(c)
                if rid not in cfm or cfm[rid].answer_type!=tfm[rid].answer_type:continue
                if reuse[c.id]>=max_reuse:continue
                candidates.append(c)
            candidates.sort(key=lambda c:match_rank(t,c,rid))
            chosen=candidates[:C]
            if len(chosen)<C:continue
            for c in chosen:reuse[c.id]+=1
            fg=sid("facet",tid,rid); facet_plans.append({"facet_group_id":fg,"relation_id":rid,"controls":[c.id for c in chosen],"template_ids":[x["template_id"] for x in bank[rid][:T]]})
            for tpl in bank[rid][:T]:
                q_t=f"{tpl['question_template'].replace('{ENTITY}',t.id)} {RESPONSE_SUFFIX}"
                tp=sid("probe",tid,t.id,rid,tpl["template_id"]); local_q[tp]={"probe_id":tp,"target_id":tid,"entity_id":t.id,"side":"target","relation_id":rid,"answer_type":tfm[rid].answer_type,"template_id":tpl["template_id"],"question":q_t,"public_value":tfm[rid].public_value,"public_aliases":tfm[rid].aliases,"public_evidence_span":tfm[rid].evidence_span}
                for c in chosen:
                    cf=facet_map(c)[rid]; q_c=f"{tpl['question_template'].replace('{ENTITY}',c.id)} {RESPONSE_SUFFIX}"
                    masked_t=norm(q_t.replace(t.id,"{ENTITY}")); masked_c=norm(q_c.replace(c.id,"{ENTITY}"))
                    assert masked_t==masked_c
                    cp=sid("probe",tid,c.id,rid,tpl["template_id"]); local_q[cp]={"probe_id":cp,"target_id":tid,"entity_id":c.id,"side":"control","relation_id":rid,"answer_type":cf.answer_type,"template_id":tpl["template_id"],"question":q_c,"public_value":cf.public_value,"public_aliases":cf.aliases,"public_evidence_span":cf.evidence_span}
                    ci=sid("cmp",tid,rid,tpl["template_id"],c.id); local_c[ci]={"comparison_id":ci,"facet_group_id":fg,"target_id":tid,"control_id":c.id,"relation_id":rid,"answer_type":tfm[rid].answer_type,"template_id":tpl["template_id"],"target_probe_id":tp,"control_probe_id":cp}
        eligible=len(facet_plans)>=min_facets
        if eligible:
            queries.update(local_q); comps.update(local_c)
        plans.append({"target_id":tid,"category":t.category,"era":t.era,"prominence_bin":t.prominence_bin,"eligible":eligible,"valid_facets":len(facet_plans),"ineligibility_reason":None if eligible else f"Only {len(facet_plans)} feasible facets; require {min_facets}","facets":facet_plans if eligible else [],"endpoint_call_count":len(local_q) if eligible else 0,"comparison_count":len(local_c) if eligible else 0})
    return plans,[queries[k] for k in sorted(queries)],[comps[k] for k in sorted(comps)]


def audit(plans,queries,comps,entities, condition:str):
    byid={e.id:e for e in entities}; qid={q["probe_id"]:q for q in queries}
    elig=[p for p in plans if p["eligible"]]
    rows=[]
    for c in comps[:80]:
        t=byid[c["target_id"]]; ctrl=byid[c["control_id"]]; tq=qid[c["target_probe_id"]]; cq=qid[c["control_probe_id"]]
        rows.append({"condition":condition,"target":t.id,"control":ctrl.id,"target_category":t.category,"control_category":ctrl.category,"target_era":t.era,"control_era":ctrl.era,"target_prominence":t.prominence_bin,"control_prominence":ctrl.prominence_bin,"relation":c["relation_id"],"target_question":tq["question"],"control_question":cq["question"]})
    return {"targets":len(plans),"eligible":len(elig),"eligibility_rate":len(elig)/max(1,len(plans)),"mean_calls":statistics.mean([p["endpoint_call_count"] for p in elig]) if elig else 0,"mean_comparisons":statistics.mean([p["comparison_count"] for p in elig]) if elig else 0,"ineligible":{p["target_id"]:p["ineligibility_reason"] for p in plans if not p["eligible"]}},rows


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out-dir",default="pathfinder_probe_pilot/output"); ap.add_argument("--pool-size",type=int,default=200); ap.add_argument("--targets",type=int,default=20); args=ap.parse_args()
    out=Path(args.out_dir); out.mkdir(parents=True,exist_ok=True)
    g=Gemini(); session=requests.Session(); session.headers.update({"User-Agent":USER_AGENT})
    names=get_rwku_names(args.pool_size); target_ids=names[:args.targets]
    print(f"[RWKU] recovered {len(names)} names; first {len(target_ids)} are targets",flush=True)
    dump_json(out/"target_ids.json",target_ids)

    raw=[]; failed=[]
    for i,name in enumerate(names,1):
        print(f"[wiki {i}/{len(names)}] {name}",flush=True)
        try:
            w=wiki_search_and_extract(name)
            if not w: failed.append({"name":name,"reason":"wikipedia_resolution"}); continue
            raw.append({"name":name,"wiki_title":w["title"],"wiki_url":w["url"],"descriptor_text":w["text"],"pageviews":pageviews(w["title"])})
        except Exception as e: failed.append({"name":name,"reason":str(e)[:200]})
        time.sleep(0.05)
    assign_prominence(raw); dump_json(out/"wikipedia_resolution_report.json",{"resolved":len(raw),"failed":failed})

    entities=[]
    extraction_failed=[]
    for i,r in enumerate(raw,1):
        print(f"[gemini entity {i}/{len(raw)}] {r['name']}",flush=True)
        try:
            ext=g.structured(extraction_prompt(r["name"],r["descriptor_text"]),ExtractedEntity)
            ext=validate_extract(r["name"],r["descriptor_text"],ext)
            entities.append(Entity(id=r["name"],wiki_title=r["wiki_title"],wiki_url=r["wiki_url"],descriptor_text=r["descriptor_text"],category=ext.category,era=ext.era,prominence_bin=r["prominence_bin"],pageviews_365d=r["pageviews"],aliases=ext.aliases,facets=ext.facets))
            dump_jsonl(out/"rwku_enriched_entities.partial.jsonl",entities)
        except Exception as e:
            extraction_failed.append({"name":r["name"],"reason":str(e)[:500]})
            print(f"  [WARN] extraction failed for {r['name']}: {e}", file=sys.stderr, flush=True)
        time.sleep(0.15)
    dump_jsonl(out/"rwku_enriched_entities.jsonl",entities)
    available={e.id for e in entities}; target_ids=[x for x in target_ids if x in available]

    rels=[rid for rid in ONTOLOGY if sum(rid in facet_map(e) for e in entities)>=3]
    bank=build_template_bank(g,rels,2); dump_json(out/"template_bank.json",{"generator_model":MODEL_ID,"templates":bank})

    conditions={}
    audit_rows=[]
    for cname,samecat in [("strict_same_category",True),("schema_relation_only",False)]:
        plans,queries,comps=build_plans(entities,target_ids,bank,samecat)
        dump_jsonl(out/f"{cname}_probe_plans.jsonl",plans); dump_jsonl(out/f"{cname}_queries.jsonl",queries); dump_jsonl(out/f"{cname}_comparisons.jsonl",comps)
        rep,rows=audit(plans,queries,comps,entities,cname); conditions[cname]=rep; audit_rows.extend(rows)
    if audit_rows:
        with (out/"audit_sample.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(audit_rows[0])); w.writeheader(); w.writerows(audit_rows)

    facet_counts=Counter(len(e.facets) for e in entities); cat_counts=Counter(e.category for e in entities); era_counts=Counter(e.era for e in entities); prom_counts=Counter(e.prominence_bin for e in entities)
    summary={
      "model":MODEL_ID,"dataset":"RWKU","pool_requested":args.pool_size,"resolved_entities":len(entities),"targets_requested":args.targets,"targets_resolved":len(target_ids),"gemini_extraction_failures":extraction_failed,
      "facet_count_distribution":dict(sorted(facet_counts.items())),"category_counts":dict(cat_counts),"era_counts":dict(era_counts),"prominence_counts":dict(prom_counts),"conditions":conditions,
      "protocol":{"max_facets":8,"min_facets":6,"templates_per_facet":2,"controls_per_facet":2,"max_control_reuse":2,"response_suffix":RESPONSE_SUFFIX,"wikipedia_pageview_window":"2025-08-01..2026-07-31"},
      "notes":["No target-model responses, membership labels, training records, or forget-set answers were used in pair construction.","RWKU target names came from the public forget_target list; descriptors came from Wikipedia, not RWKU forget probes.","The schema_relation_only condition is a feasibility/matching ablation; strict_same_category is the candidate main protocol."]
    }
    dump_json(out/"build_report.json",summary)
    md=["# PATHFINDER Strict Matched-Probe Pilot",f"- Gemini model: `{MODEL_ID}`",f"- RWKU public-person pool resolved: **{len(entities)}** / {args.pool_size}",f"- Target identities evaluated for probe feasibility: **{len(target_ids)}**",""]
    for cname,rep in conditions.items():
        md += [f"## {cname}",f"- Eligible targets: **{rep['eligible']} / {rep['targets']}** ({100*rep['eligibility_rate']:.1f}%)",f"- Mean unique endpoint calls among eligible targets: **{rep['mean_calls']:.1f}**",f"- Mean target-control comparisons: **{rep['mean_comparisons']:.1f}",""]
    md += ["## Scientific interpretation","This pilot tests probe-construction feasibility only. It does not query an unlearned target model and therefore does not measure membership-inference power.","The key outcome is whether strict public-information matching can supply at least six distinct shared facets for most held-out RWKU targets while preserving exact target/control template identity."]
    (out/"RESULTS.md").write_text("\n".join(md),encoding="utf-8")
    print(json.dumps(summary,indent=2),flush=True)

if __name__=="__main__": main()
