from tenacity import retry, wait_exponential, stop_after_attempt
from openai import OpenAI
import os
import sys
import yaml
from typing import Dict, Any, Literal
import json
from tqdm import tqdm
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor, as_completed

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, ".."))
sys.path.append(current_dir)
from configs import CommonConfig


def load_judge_config():
    current_dir = os.path.dirname(os.path.abspath(__file__))

    judge_config_path = os.path.join(current_dir, '../configs', 'judge_config.yaml')
    
    with open(judge_config_path, 'rb') as f:
        judge_config = yaml.safe_load(f)
    # print(judge_config)
    return judge_config

def eval_llm(item, judge_model):
    # breakpoint()
    judge_config = load_judge_config()
    model_config = CommonConfig["O3-MINI_CONFIG"]
    evaluation_prompt = judge_config['HLE_eval_prompt_template'].format(question=item['query'], response=item['solution'].split('</think>')[-1].split('</execution_results>')[-1].strip(), correct_answer=item['gt'])
    try:
        response = call_llm(evaluation_prompt, model_config)
            
    except Exception as e:
        response = 'calling llm error'

    if "correct: yes" in response:
        score = 2
    else:
        score = 0
    item['evaluation'] = response
    item['score'] = score

    return item



def handle_retry_error(retry_state):
    print('retry ')
    return ''

class ExtractedAnswer(BaseModel):
    extracted_final_answer: str
    reasoning: str
    correct: Literal["yes", "no"]
    confidence: int
    strict: Literal[True] # 100% reliability

@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5), retry_error_callback=handle_retry_error)
def call_llm(prompt, model_config:Dict[str, Any]):
    model_url = model_config['url']
    model_name = model_config['model_name']
    max_tokens = model_config['max_tokens']

    llm = OpenAI(base_url=f"{model_url}", api_key=model_config["authorization"])

    completion = llm.beta.chat.completions.parse(
        model=f"{model_name}",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=max_tokens,
        response_format=ExtractedAnswer
    )

    # breakpoint()
    content = completion.choices[0].message.parsed
    print("content.correct: ", content.correct)
    correct = int("yes" in content.correct.lower())
    if correct == 1:
        return "correct: yes"
    else:
        return "correct: no"


def score(judge_model:str, data_path):
    with open(data_path, 'rb') as f:
        data = f.readlines()

    infer_data = [json.loads(obj) for obj in data]
    lookup_table = {json.loads(obj)['query']:0 for obj in data}

    output_jsonl_path = data_path.replace(".jsonl", f"_{judge_model}_eval.jsonl")
    total_num = len(infer_data)
    correct_num = 0
    if os.path.exists(output_jsonl_path):
        with open(output_jsonl_path, 'rb') as f:
            processed_data = f.readlines()
        for obj in processed_data:
            lookup_table[json.loads(obj)['query']] = 1
            correct_num += json.loads(obj)['score'] == 2
    
    need_process_infer_data = [item for item in infer_data if not lookup_table[item['query']]]
    print(f"==> processing {data_path.split('/')[-1]}, {len(need_process_infer_data)} need to process...")


    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(eval_llm, item, judge_model) for item in need_process_infer_data]

        for future in tqdm(as_completed(futures), total=len(need_process_infer_data), desc="processing"):
            result = future.result()
            if result['score'] == 2:
                correct_num += 1
            if result:
                with open(output_jsonl_path, 'a') as f:
                    f.write(json.dumps(result) + '\n')
                    f.flush() 
    print(f"==> {data_path.split('/')[-1]} evaluation done, {correct_num}/{total_num} correct")
    
    


if __name__ == '__main__':

    judge_model = "o3-mini"
    data_path = "results/hle_8_22.jsonl"

    score(judge_model, data_path)