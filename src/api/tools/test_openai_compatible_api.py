#!/usr/bin/env python3
import os
import sys
import json
import requests
import argparse
from dotenv import load_dotenv

load_dotenv()


def test_openai_compatible_api(messages, api_url, api_key):
    """OpenAI互換APIをテストする関数

    Args:
        messages (list): 送信するメッセージのリスト
        api_url (str): APIのURL
        api_key (str): APIキー
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    data = {"model": "gpt-4", "messages": messages, "stream": True}

    response = requests.post(api_url, headers=headers, json=data, stream=True)

    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return

    for line in response.iter_lines():
        if line:
            line = line.decode("utf-8")
            if line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    json_data = json.loads(data)
                    content = json_data["choices"][0]["delta"].get("content", "")
                    if content:
                        print(content, end="", flush=True)
                except json.JSONDecodeError:
                    print(f"Error parsing JSON: {data}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test OpenAI Compatible API")
    parser.add_argument("--message", type=str, default="こんにちは", help="Message to send")
    parser.add_argument("--url", type=str, default="http://localhost:8000/v1/chat/completions", help="API URL")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_COMPATIBLE_API_KEY")
    if not api_key:
        print("Error: OPENAI_COMPATIBLE_API_KEY environment variable is not set")
        sys.exit(1)

    messages = [{"role": "user", "content": args.message}]
    test_openai_compatible_api(messages, args.url, api_key)
