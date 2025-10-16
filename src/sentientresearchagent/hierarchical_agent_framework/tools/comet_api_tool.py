import requests
from typing import Optional

class CometAPITool:
    """
    Simple integration layer for CometAPI — enables ROMA agents
    to query Comet’s LLM or multimodal endpoints.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.cometapi.com/v1"):
        self.api_key = api_key
        self.base_url = base_url

    def query(self, prompt: str, model: str = "gpt-4", max_tokens: int = 512) -> Optional[str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens
        }
        response = requests.post(f"{self.base_url}/generate", headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json().get("output", "")
        else:
            print(f"CometAPI error {response.status_code}: {response.text}")
            return None
