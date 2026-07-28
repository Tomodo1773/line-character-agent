"""データセットをエージェントに流し、ツール呼び出しとキャラクター応答を採点する（ADR-0001 §5）。

3つの採点を同じ実行で行う。

- **Foundry Evaluations**: 組み込みのエージェント評価器（intent resolution / tool call accuracy /
  task adherence）をジャッジモデルで実行する。結果は Foundry ポータルにも残る。
- **ローカル照合**: データセットに書いた期待ツールと実際の呼び出しを突き合わせる。LLM を使わないので
  ぶれない。あわせて、期待していない書き込み系ツールを呼んでいないかも見る。
- **キャラクター応答**: システムプロンプトを基準にしたジャッジで 1-5 点を付ける。

使い方は `evals/README.md` を参照。既定モデルと代替候補で `--model` を変えて2回実行し、比較する。
"""

import argparse
import asyncio
import os
from typing import Any

from agent_framework import (
    Agent,
    AgentEvalConverter,
    EvalItem,
    EvalResults,
    LocalEvaluator,
    Message,
    evaluator,
    tool_call_args_match,
)
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from azure.identity import DefaultAzureCredential

from character_agent.agent import create_agent
from character_agent.config import create_logger, get_settings
from evals.character import PASS_THRESHOLD, score_character
from evals.dataset import Case, load_cases
from evals.fake_backend import EVAL_USER_ID, fake_backend

logger = create_logger(__name__)

# ADR-0001 §5 が挙げるエージェント評価器。
FOUNDRY_EVALUATORS = [FoundryEvals.INTENT_RESOLUTION, FoundryEvals.TOOL_CALL_ACCURACY, FoundryEvals.TASK_ADHERENCE]

# 呼ばれると日記が変わってしまうツール。期待していないケースで呼んでいたら失敗とする。
WRITE_TOOLS = {"diary_create", "diary_update", "diary_delete", "diary_rename", "digest_regenerate"}


@evaluator(name="no_unexpected_write")
def no_unexpected_write(conversation: list[Message], expected_tool_calls: list[Any] | None) -> dict[str, Any]:
    """期待していない書き込み系ツールを呼んでいないか見る。曖昧な依頼で勝手に消させないための歯止め。"""
    expected = {call.name for call in expected_tool_calls or []}
    called = {
        content.name
        for message in conversation
        for content in message.contents or []
        if content.type == "function_call" and content.name
    }
    unexpected = sorted((called & WRITE_TOOLS) - expected)
    return {"passed": not unexpected, "reason": f"想定外の書き込み: {unexpected}" if unexpected else "想定外の書き込みなし"}


async def run_case(agent: Agent, case: Case) -> EvalItem:
    """1ケース分の会話をエージェントに実行させ、評価器に渡す形にまとめる。"""
    logger.info("run_case が呼び出されました: id=%s", case.id)
    session = agent.create_session()
    history: list[Message] = []
    with fake_backend():
        # 最後の発話への応答を採点する。それより前のターンは会話の文脈として履歴に積むだけ。
        for turn in case.turns[:-1]:
            history.append(Message("user", [turn]))
            history.extend((await agent.run([history[-1]], session=session)).messages)
        history.append(Message("user", [case.turns[-1]]))
        response = await agent.run([history[-1]], session=session)

    item = AgentEvalConverter.to_eval_item(query=history, response=response, agent=agent)
    item.expected_tool_calls = case.expected_tools
    return item


async def evaluate(model: str | None, judge_model: str) -> None:
    """データセット全件を実行して採点し、結果を出力する。"""
    logger.info("evaluate が呼び出されました: model=%s, judge_model=%s", model, judge_model)
    agent = create_agent(model=model)
    cases = load_cases()
    items = [await run_case(agent, case) for case in cases]

    judge = FoundryChatClient(
        project_endpoint=get_settings().foundry_project_endpoint,
        model=judge_model,
        credential=DefaultAzureCredential(),
    )
    eval_name = f"character-agent eval ({model or get_settings().model_deployment_name})"
    local_results = await LocalEvaluator(tool_call_args_match, no_unexpected_write).evaluate(items, eval_name=eval_name)
    foundry_results = await FoundryEvals(client=judge, evaluators=FOUNDRY_EVALUATORS).evaluate(items, eval_name=eval_name)
    character_scores = [await score_character(judge, item.query, item.response) for item in items]

    logger.info("%s", _report(eval_name, cases, local_results, foundry_results, character_scores))


def _report(
    eval_name: str,
    cases: list[Case],
    local: EvalResults,
    foundry: EvalResults,
    character_scores: list[tuple[int, str]],
) -> str:
    lines = [f"\n=== {eval_name} / {len(cases)} ケース ==="]

    lines.append("\n[ローカル照合]")
    lines += [f"  {name}: {counts['passed']}/{len(cases)} 合格" for name, counts in local.per_evaluator.items()]
    lines += [
        f"  × {case.id}: {score.name} — {(score.sample or {}).get('reason', '')}"
        for case, result in zip(cases, local.items)
        for score in result.scores
        if not score.passed
    ]

    lines.append(f"\n[Foundry Evaluations] status={foundry.status}")
    lines += [
        f"  {name}: {counts['passed']}/{counts['passed'] + counts['failed']} 合格"
        for name, counts in foundry.per_evaluator.items()
    ]
    if foundry.error:
        lines.append(f"  エラー: {foundry.error}")
    if foundry.report_url:
        lines.append(f"  レポート: {foundry.report_url}")

    average = sum(score for score, _ in character_scores) / len(character_scores)
    below = sum(1 for score, _ in character_scores if score < PASS_THRESHOLD)
    lines.append(f"\n[キャラクター応答] 平均 {average:.2f} / 5.00（{PASS_THRESHOLD} 点未満 {below} 件）")
    lines += [f"  {case.id}: {score} — {reason}" for case, (score, reason) in zip(cases, character_scores)]

    return "\n".join(lines)


def _prepare_environment() -> None:
    """評価では使わない設定にダミー値を入れる。

    Cosmos DB と埋め込みは `fake_backend` が差し替えるため接続しないが、設定は起動時に一括検証される。
    """
    os.environ.setdefault("COSMOS_DB_ACCOUNT_URL", "https://eval.invalid/")
    os.environ.setdefault("DIARY_USER_ID", EVAL_USER_ID)
    os.environ.setdefault("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", "unused-in-eval")


def main() -> None:
    parser = argparse.ArgumentParser(description="キャラクターエージェントの評価を実行する")
    parser.add_argument("--model", help="評価するモデルのデプロイ名（既定: AZURE_AI_MODEL_DEPLOYMENT_NAME）")
    parser.add_argument(
        "--judge-model",
        default=os.environ.get("EVAL_JUDGE_DEPLOYMENT_NAME"),
        help="採点に使うモデルのデプロイ名（既定: EVAL_JUDGE_DEPLOYMENT_NAME）",
    )
    args = parser.parse_args()
    if not args.judge_model:
        parser.error("--judge-model か環境変数 EVAL_JUDGE_DEPLOYMENT_NAME でジャッジモデルのデプロイ名を指定してください")

    _prepare_environment()
    asyncio.run(evaluate(args.model, args.judge_model))


if __name__ == "__main__":
    main()
