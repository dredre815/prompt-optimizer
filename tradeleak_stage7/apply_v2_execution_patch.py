from pathlib import Path

p = Path(__file__).with_name("runner.py")
s = p.read_text(encoding="utf-8")

replacements = [
    (
        "import decoupledmarket.content.gpt_structure as gs\nfrom decoupledmarket.content.our_run_gpt_prompt import run_gpt_prompt_trading_stock\n",
        "import decoupledmarket.content.gpt_structure as gs\nimport decoupledmarket.content.our_run_gpt_prompt as orp\nfrom decoupledmarket.content.our_run_gpt_prompt import run_gpt_prompt_trading_stock\n",
    ),
    (
        "MODEL='deepseek-v4-flash';client=OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'],base_url='https://api.deepseek.com',timeout=90,max_retries=2)\nSEED=20260819; random.seed(SEED); np.random.seed(SEED); REPS=3\n",
        "MODEL='deepseek-v4-flash';NATIVE_REPEAT_CAP=3;PROVIDER_ATTEMPTS=2;REQUEST_TIMEOUT_SEC=60;MAX_COMPLETION_TOKENS=4096\nclient=OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'],base_url='https://api.deepseek.com',timeout=REQUEST_TIMEOUT_SEC,max_retries=0)\nAPI_STATS={'provider_calls':0,'provider_errors':0,'provider_success_empty':0,'provider_success_nonempty':0,'finish_reasons':{},'llm_requested_repeats':[],'chatgpt_requested_repeats':[]}\nSEED=20260819; random.seed(SEED); np.random.seed(SEED); REPS=1\n",
    ),
    (
        "def ds_request(agent_model,prompt):\n last=''\n for k in range(3):\n  try:\n   r=client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],temperature=.15,max_tokens=1024); last=r.choices[0].message.content or ''\n   if last.strip(): return last\n  except Exception: time.sleep(1.2*(k+1))\n return last\ngs._request_by_model=ds_request; gs.temp_sleep=lambda seconds=1:None\n",
        "def ds_request(agent_model,prompt):\n last=''\n for k in range(PROVIDER_ATTEMPTS):\n  API_STATS['provider_calls']+=1\n  try:\n   r=client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],temperature=.15,max_tokens=MAX_COMPLETION_TOKENS)\n   choice=r.choices[0];reason=str(getattr(choice,'finish_reason',None));API_STATS['finish_reasons'][reason]=API_STATS['finish_reasons'].get(reason,0)+1;last=choice.message.content or ''\n   if last.strip(): API_STATS['provider_success_nonempty']+=1;return last\n   API_STATS['provider_success_empty']+=1\n  except Exception:\n   API_STATS['provider_errors']+=1;time.sleep(1.2*(k+1))\n return last\ngs._request_by_model=ds_request; gs.temp_sleep=lambda seconds=1:None\n_ORIGINAL_LLM_SAFE=gs.llm_safe_generate_response\n_ORIGINAL_CHATGPT_SAFE=gs.ChatGPT_safe_generate_response\ndef bounded_llm_safe_generate_response(persona,prompt,example_output,special_instruction,repeat=3,fail_safe_response='error',func_validate=None,func_clean_up=None,verbose=False,virtual_date=None,iteration=None):\n API_STATS['llm_requested_repeats'].append(int(repeat))\n return _ORIGINAL_LLM_SAFE(persona,prompt,example_output,special_instruction,min(int(repeat),NATIVE_REPEAT_CAP),fail_safe_response,func_validate,func_clean_up,False,virtual_date=virtual_date,iteration=iteration)\ndef bounded_chatgpt_safe_generate_response(persona,prompt,example_output,special_instruction,repeat=3,fail_safe_response='error',func_validate=None,func_clean_up=None,verbose=False,virtual_date=None,iteration=None):\n API_STATS['chatgpt_requested_repeats'].append(int(repeat))\n return _ORIGINAL_CHATGPT_SAFE(persona,prompt,example_output,special_instruction,min(int(repeat),NATIVE_REPEAT_CAP),fail_safe_response,func_validate,func_clean_up,False,virtual_date=virtual_date,iteration=iteration)\norp.llm_safe_generate_response=bounded_llm_safe_generate_response\norp.ChatGPT_safe_generate_response=bounded_chatgpt_safe_generate_response\n",
    ),
    (
        "'gate':'ON recovery AUC>=0.75 AND OFF<=0.65 AND delta>=0.15 AND valid>=0.90','verdict':'GO' if go else 'NO-GO'}",
        "'scientific_design_changed':True,'exploratory_fast_screen':True,'primary_gate_applicable':False,'execution_addendum':{'native_repeat_cap':NATIVE_REPEAT_CAP,'provider_attempts':PROVIDER_ATTEMPTS,'request_timeout_sec':REQUEST_TIMEOUT_SEC,'max_completion_tokens':MAX_COMPLETION_TOKENS,'semantic_parser_adapter':False,'chatgpt_and_llm_generators_capped':True},'api_stats':API_STATS,'gate':'DESCRIPTIVE ONLY; primary Stage-7 gate not applicable to REPS=1 fast screen','verdict':'EXPLORATORY'}",
    ),
]

for old, new in replacements:
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"Stage-7 fast-screen patch expected exactly one match, got {count}: {old[:120]!r}")
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("Applied preregistered Stage-7 exploratory fast-screen patch: REPS=1 + correct native caps")
