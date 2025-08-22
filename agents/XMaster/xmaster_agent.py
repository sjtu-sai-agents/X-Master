import os
import re
import sys
import json
import argparse
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, "../.."))
sys.path.append(current_dir)

from configs import CommonConfig


def strip_think_and_exec(text: str) -> str:
    """Keep only the visible answer part by removing </think> ... and </execution_results> tails."""
    if text is None:
        return ""
    out = text
    if "</think>" in out:
        out = out.split("</think>")[-1]
    if "</execution_results>" in out:
        out = out.split("</execution_results>")[-1]
    return out.strip()


class LLMAgent:

    def __init__(self, model_url: str, model_key, toolbox_url: str, max_tokens: int = 64000, temperature: float = 0.5):
        self.llm_config: Dict[str, Any] = {
            'model': 'deepseek-r1',
            'base_url': model_url,
            'api_key': model_key,
            'generation_config': {
                'max_tokens': max_tokens,
                'temperature': temperature,
            },
            'stop_condition': r'<code[^>]*>((?:(?!<code).)*?)</code>',
            'tool_condition': r'<code[^>]*>((?:(?!<code).)*?)</code>',
        }
        self.toolbox_url = toolbox_url

        template_path = os.path.join(current_dir, '../../configs/templates/r1_tool.jinja')
        with open(template_path, 'r', encoding='utf-8') as f:
            self.chat_template = f.read()


    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=0.5, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def call_model(self, user_prompt: str, assistant_prefix: str) -> str:
        """Run one conversation (think-while-calling-tools loop) and return rendered output."""
        from llm_agent.base_agent import BaseAgent
        from llm_agent.context import BaseContextManager
        from llm_agent.tools.tool_manager import BaseToolManager

        # Build fresh instances to ensure thread-safety
        base_agent = BaseAgent(llm_config=self.llm_config)
        context_manager = BaseContextManager(chat_template=self.chat_template)
        tool_manager = BaseToolManager(url=self.toolbox_url)

        # Seed logs
        context_manager.agent_logs = [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_prefix},
        ]

        # Main loop
        while True:
            prompt = context_manager.build_input_prompt()
            result = base_agent.step(prompt)
            context_manager.log_agent(result.get('step_response', ''))
            print(f"Agent response: {result.get('step_response', '')}")

            tool_call_content = result.get('tool_call_content')
            if not tool_call_content:
                break

            context_manager.log_tool_call(tool_call_content)
            tool_result = tool_manager.execute_tool(tool_call_content)
            context_manager.log_tool_call_result(tool_result)
            print(f"Tool call content: {tool_call_content}")
            print(f"\033[32mTool call result: {tool_result}\033[0m")

        # Render final response with template
        return context_manager.chat_template.render(tool_logs=context_manager.agent_logs)


class XMasterAgent:
    def __init__(self, debug: bool = False):
        self.deepseek_api_url = CommonConfig['DEEPSEEK_0528_CONFIG']['url']
        self.deepseek_api_key = CommonConfig['DEEPSEEK_0528_CONFIG']['authorization']
        self.sandbox_url = CommonConfig['SANDBOX']['tool_link']
        self.chat_obj = LLMAgent(self.deepseek_api_url, self.deepseek_api_key, self.sandbox_url)
        self.debug = debug

    # ---- Stage runners ----

    def _forward_solver(self, query: str) -> str:
        user_prompt = CommonConfig["SOLVER_PROMPT"]["user_prompt"].format(query=query)
        assistant_prefix = CommonConfig["SOLVER_PROMPT"]["assistant_prefix"]

        return self.chat_obj.call_model(user_prompt, assistant_prefix)

    def _forward_critic(self, query: str, student_solution: str) -> str:
        s_solution = strip_think_and_exec(student_solution)
        user_prompt = CommonConfig["CRITIC_PROMPT"]["user_prompt"].format(query=query, s_solution=s_solution)
        assistant_prefix = CommonConfig["CRITIC_PROMPT"]["assistant_prefix"]
    
        return self.chat_obj.call_model(user_prompt, assistant_prefix)

    def _forward_rewrite(self, query: str, candidates: List[str]) -> str:
        assert len(candidates) == 5, "rewrite expects exactly 5 candidates"
        cands = [strip_think_and_exec(x) for x in candidates]
        user_prompt = CommonConfig["REWRITE_PROMPT"]["user_prompt"].format(query=query,
                                                                        solution_1=cands[0],
                                                                        solution_2=cands[1],
                                                                        solution_3=cands[2],
                                                                        solution_4=cands[3],
                                                                        solution_5=cands[4])
        assistant_prefix = CommonConfig["REWRITE_PROMPT"]["assistant_prefix"]

        return self.chat_obj.call_model(user_prompt, assistant_prefix)

    def _forward_selector(self, query: str, candidates: List[str]) -> str:
        assert len(candidates) == 5, "selector expects exactly 5 candidates"

        user_prompt = CommonConfig["SELECTOR_PROMPT"]["user_prompt"].format(query=query, 
                                                                        solution_1=strip_think_and_exec(candidates[0]),
                                                                        solution_2=strip_think_and_exec(candidates[1]),
                                                                        solution_3=strip_think_and_exec(candidates[2]),
                                                                        solution_4=strip_think_and_exec(candidates[3]),
                                                                        solution_5=strip_think_and_exec(candidates[4]))
        assistant_prefix = CommonConfig["SELECTOR_PROMPT"]["assistant_prefix"]

        selector_response = self.chat_obj.call_model(user_prompt, assistant_prefix)
        m = re.search(r'<select>Response (\d+)</select>', selector_response)
        if not m:
            print("Warning: Could not parse selector's decision. Defaulting to Response 1.")
            idx = 0
        else:
            idx = max(0, min(4, int(m.group(1)) - 1))
        return candidates[idx]

    # ---- Full pipeline ----
    def forward(self, query: str) -> str:
        """Run the pipeline: solver(5, parallel) -> critic(5, parallel) -> rewrite(5, parallel) -> selector."""
        print("Step 1 | Solver : Generating 5 solutions in parallel...")
        solutions: List[str] = ["" for _ in range(5)]
        with ThreadPoolExecutor(max_workers=5) as ex:
            fut2idx = {ex.submit(self._forward_solver, query): i for i in range(5)}
            for fut in as_completed(fut2idx):
                solutions[fut2idx[fut]] = fut.result()

        print("Step 2 | Critic : Critiquing each solution in parallel...")
        critic_solutions: List[str] = ["" for _ in range(5)]
        with ThreadPoolExecutor(max_workers=5) as ex:
            fut2idx = {ex.submit(self._forward_critic, query, solutions[i]): i for i in range(5)}
            for fut in as_completed(fut2idx):
                critic_solutions[fut2idx[fut]] = fut.result()

        print("Step 3 | Rewrite : Rewriting 5 solutions in parallel...")
        rewrite_solutions: List[str] = ["" for _ in range(5)]
        with ThreadPoolExecutor(max_workers=5) as ex:
            fut2idx = {ex.submit(self._forward_rewrite, query, critic_solutions): i for i in range(5)}
            for fut in as_completed(fut2idx):
                rewrite_solutions[fut2idx[fut]] = fut.result()

        print("Step 4 | Selector : Selecting the best solution...")
        final_solution: str = self._forward_selector(query, rewrite_solutions)

        if self.debug:
            dump = {
                "query": query,
                "solutions": solutions,
                "critic_solutions": critic_solutions,
                "rewrite_solutions": rewrite_solutions,
                "final_solution": final_solution,
            }
            with open("pipeline_debug.json", "w", encoding="utf-8") as f:
                json.dump(dump, f, ensure_ascii=False, indent=2)
            # Optional breakpoint for interactive debug
            # import pdb; pdb.set_trace()

        return final_solution


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run XMasterAgent with a query.")
    parser.add_argument('--query', type=str, default="What is the largest order of a non-cyclic torsion subgroup of an elliptic curve over $\\mathbb{Q}(\\sqrt{-3})$?", help='The query to process.')
    args = parser.parse_args()
    
    agent = XMasterAgent()
    out = agent.forward(args.query)
    print("Final solution:", out)
