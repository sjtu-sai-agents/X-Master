from agents.XMaster.xmaster_agent import XMasterAgent
import json
import os
import json
from typing import Any, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed


def agent_forward(query:str):
    xmaster_agent = XMasterAgent()

    solution = xmaster_agent.forward(query=query)
    return solution

def process_one(item: Any) -> Dict[str, Any]:
    """Run the agent for one item and persist result. Skips if file already exists."""
    query = item["query"]

    # Create agent instance per task for thread safety
    agent = XMasterAgent()
    final_solution = agent.forward(query=query)

    item["solution"] = final_solution
    return item


def main(save_data_path):
    data_path = "data/hle.json"

    with open(data_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    total = len(dataset)
    print(f"\033[32mLoaded dataset with {total} items.\033[32m")

    max_workers = 8

    # Pre-skip: count existing
    if os.path.exists(save_data_path):
        with open(save_data_path, "r", encoding="utf-8") as f:
            proccessed_data = [json.loads(line) for line in f.readlines()]
        processed_ids = [item["id"] for item in proccessed_data]
    else:
        processed_ids = []

    while len(processed_ids) < total:
        to_be_processed = [item for item in dataset if item["id"] not in processed_ids]
        print(f"\033[32mTo be processed: {len(to_be_processed)} items.\033[0m")
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut2idx = {ex.submit(process_one, item): item for item in to_be_processed}
            for future in as_completed(fut2idx):
                item = fut2idx[future]
                try:
                    result = future.result()
                    if result:
                        with open(save_data_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(result, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"\033[31m[ERROR] in {item['id']}: {e} \033[0m")

    # Summary
    with open(save_data_path, "r", encoding="utf-8") as f:
        final_data = [json.loads(line) for line in f.readlines()]
    print(f"\033[32mFinal dataset size: {len(final_data)}\033[32m")


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    
    save_data_path = "results/hle_8_22.jsonl"
    main(save_data_path)


