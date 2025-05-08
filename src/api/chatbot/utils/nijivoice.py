import requests
import json
from typing import Dict, Any, Optional
import os


class NijiVoiceClient:
    BASE_URL = "https://api.nijivoice.com/api/platform/v1"
    DEFAULT_API_KEY = os.getenv("NIJIVOICE_API_KEY")

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.headers = {"accept": "application/json", "content-type": "application/json", "x-api-key": self.api_key}

    def get_actors(self) -> Dict[str, Any]:
        """音声アクターの一覧を取得"""
        url = f"{self.BASE_URL}/voice-actors"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def generate(
        self,
        script: str,
        voice_actor_id: str = "249d8d02-2c25-4a24-8faf-26d6f734b7bc",
        format: str = "mp3",
        speed: str = "1.0",
    ) -> Dict[str, Any]:
        """音声を生成"""
        url = f"{self.BASE_URL}/voice-actors/{voice_actor_id}/generate-voice"

        payload = {"format": format, "speed": speed, "script": script}

        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    client = NijiVoiceClient()

    # 音声アクター一覧の取得
    # voice_actors = client.get_actors()
    # print(json.dumps(voice_actors, indent=4, ensure_ascii=False))

    # 音声の生成
    generated_voice = client.generate("こんにちは")
    print(json.dumps(generated_voice, indent=4, ensure_ascii=False))
