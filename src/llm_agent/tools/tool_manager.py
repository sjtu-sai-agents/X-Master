from uuid import uuid4
import requests




class BaseToolManager:
    def __init__(self, url:str):
        self.server_url = url
        self.headers = {
            "Content-Type": "application/json"
        }

    def execute_tool(self, tool_call:str):
        # tool_call = "from tools import *\n" + tool_call
        payload = {
            "code":tool_call
        }
        # print("execution...")
        resp = requests.post(
            f"{self.server_url}/execute",
            headers=self.headers,
            json=payload
        )

        return resp.json()





