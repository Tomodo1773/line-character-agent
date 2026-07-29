"""キャラクター応答の採点（LLM ジャッジ）。

ツール呼び出しの正しさは Foundry の組み込み評価器とローカルの照合で測れるが、「お姉さんキャラとして
成立しているか」「日本語として自然か」は本アプリ固有の基準になるため、システムプロンプトそのものを
判定基準としてジャッジモデルに渡す。ADR-0001 のリスク「オープンウェイトモデルの日本語品質は未検証」を
モデル比較の数値にするための評価軸。
"""

import json

from agent_framework import BaseChatClient, Message

from character_agent.config import create_logger
from character_agent.prompts import CHARACTER_PROMPT

logger = create_logger(__name__)

MIN_SCORE = 1
MAX_SCORE = 5
PASS_THRESHOLD = 3

_JUDGE_INSTRUCTIONS = f"""あなたはキャラクター応答の採点者です。あるチャットボットの応答が、与えられたキャラクター定義に沿っているかを {MIN_SCORE}-{MAX_SCORE} で採点してください。

## キャラクター定義
{CHARACTER_PROMPT}

## 採点の観点
- 口調と距離感が定義どおりか（タメ口、余裕のあるトーン、禁止事項を犯していないか）
- 日本語として自然か（翻訳調、不自然な語順、意味の通らない言い回しがないか）
- 依頼への応答として成立しているか（ツールの結果を機械的に読み上げるだけになっていないか）

## 点数の目安
- 5: キャラクターとして違和感がなく、日本語も自然
- 4: おおむね良いが、口調か自然さにわずかな揺れがある
- 3: 意味は通るが、キャラクターらしさが薄いか、言い回しに不自然さがある
- 2: 敬語や丁寧構文が混ざる、日本語が不自然など、明確な逸脱がある
- 1: 別人格の応答か、日本語として破綻している

reason は日本語で1-2文。"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "character_score",
        "schema": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": MIN_SCORE, "maximum": MAX_SCORE},
                "reason": {"type": "string"},
            },
            "required": ["score", "reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


async def score_character(client: BaseChatClient, query: str, response: str) -> tuple[int, str]:
    """利用者の発話とエージェントの応答を渡し、キャラクター適合度の点数と理由を得る。"""
    logger.info("score_character が呼び出されました")
    judgement = await client.get_response(
        [
            Message("system", [_JUDGE_INSTRUCTIONS]),
            Message("user", [f"## 利用者の発話\n{query}\n\n## エージェントの応答\n{response}"]),
        ],
        options={"response_format": _RESPONSE_FORMAT, "temperature": 0.0},
    )
    scored = json.loads(judgement.text)
    return int(scored["score"]), str(scored["reason"])
