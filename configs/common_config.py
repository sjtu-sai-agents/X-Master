"""Common" variables."""
from configs.prompts import *

class CommonConfig:
    def __init__(self, ):
        self.__dict__ = {
            "DEEPSEEK_0528_CONFIG": { 
                "url": "http://",
                "authorization": "EMPTY",
            },
            "O3-MINI_CONFIG": { 
                "model_name": "o3-mini",
                "url": "http://",
                "authorization": "EMPTY",
                "max_tokens": 4096,
            },
            "SANDBOX": {
                "tool_link": "http://10.200.0.53:30007"
            },
            "SOLVER_PROMPT": {
                "user_prompt": SolverPrompt_User_Template,
                "assistant_prefix": SolverPrompt_Assistant_Template
            },
            "CRITIC_PROMPT": {
                "user_prompt": CriticPrompt_User_Template,
                "assistant_prefix": CriticPrompt_Assistant_Template
            },
            "REWRITE_PROMPT": {
                "user_prompt": RewritePrompt_User_Template,
                "assistant_prefix": RewritePrompt_Assistant_Template
            },
            "SELECTOR_PROMPT": {
                "user_prompt": SelectPrompt_User_Template,
                "assistant_prefix": SelectPrompt_Assistant_Template
            },
            
        }

    def __getitem__(self, key):
        return self.__dict__.get(key, None)