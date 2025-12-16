"""Google Drive設定の確認と初期化のためのユーティリティモジュール。

このモジュールは、character.pyとdiary_workflow.pyの両方で使用される
Google Drive設定の確認ロジックを提供します。
"""

from langchain_core.messages import AIMessage
from langgraph.types import Command, interrupt

from chatbot.database.repositories import UserRepository
from chatbot.utils.config import create_logger
from chatbot.utils.drive_folder import extract_drive_folder_id
from chatbot.utils.google_auth import GoogleDriveOAuthManager

logger = create_logger(__name__)


def ensure_google_settings(userid: str, success_goto: str | list[str]) -> Command[str | list[str]]:
    """
    Google DriveのOAuth設定とフォルダIDの有無を確認し、適切なCommandを返す。

    この関数は、以下の順序でGoogle Drive設定をチェックします:
    1. OAuth認証情報の存在確認 → ない場合は認証URLを返して終了
    2. フォルダIDの存在確認 → ない場合はinterruptで入力を要求
    3. すべて揃っている場合は、success_gotoで指定されたノードへ遷移

    Args:
        userid (str): ユーザーID。
        success_goto (str | list[str]): 設定が揃った場合に遷移するノード名。
                                         文字列または文字列のリスト（並列実行用）。

    Returns:
        Command[str | list[str]]: 次の状態への遷移を表すCommand。
                                  - OAuth未設定: __end__への遷移（認証URL付き）
                                  - フォルダID未設定: success_gotoへの遷移（登録完了メッセージ付き）
                                  - すべて設定済み: success_gotoへの遷移

    Note:
        この関数内のinterruptはtry-catchで囲んではいけません。
        interruptは例外メカニズムを利用しているためです。
    """
    logger.info("--- Ensure Google Settings ---")

    # DI: CosmosClient から UserRepository を作成
    from chatbot.agent.tools import get_cosmos_client
    from chatbot.database.core import CosmosCore

    cosmos_client = get_cosmos_client()
    cosmos_core = CosmosCore(cosmos_client, "users")
    user_repository = UserRepository(cosmos_core)
    oauth_manager = GoogleDriveOAuthManager(user_repository)

    # OAuth認証情報のチェック
    credentials = oauth_manager.get_user_credentials(userid)
    if not credentials:
        return _create_auth_required_command(oauth_manager, userid)

    # フォルダIDのチェック
    folder_id = user_repository.fetch_drive_folder_id(userid)
    if folder_id:
        goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
        logger.info("Google Drive folder ID already set for user. Going to %s.", goto_desc)
        return Command(goto=success_goto)

    # フォルダIDが未設定の場合、interruptで入力を要求
    return _handle_folder_id_registration(user_repository, userid, success_goto)


def _create_auth_required_command(oauth_manager: GoogleDriveOAuthManager, userid: str) -> Command[str]:
    """
    OAuth認証が必要な場合のCommandを生成する。

    Args:
        oauth_manager: GoogleDriveOAuthManagerインスタンス
        userid: ユーザーID

    Returns:
        Command[str]: __end__への遷移と認証URLメッセージを含むCommand
    """
    logger.info("Google credentials not found for user. Generating auth URL.")
    # OAuth の state には userid を渡す
    auth_url, _ = oauth_manager.generate_authorization_url(userid)
    message = f"""Google Drive へのアクセス許可がまだ設定されていないみたい。
以下のURLから認可してね。
{auth_url}""".strip()

    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=message)]},
    )


def _handle_folder_id_registration(
    user_repository: UserRepository, userid: str, success_goto: str | list[str]
) -> Command[str | list[str]]:
    """
    フォルダIDの登録を処理する。

    interruptを使用してユーザーからフォルダIDを取得し、
    抽出・検証・保存を行います。

    Args:
        user_repository: UserRepositoryインスタンス
        userid: ユーザーID
        success_goto: 登録成功時の遷移先ノード名（文字列またはリスト）

    Returns:
        Command[str | list[str]]: 登録結果に応じたCommand
                                  - 成功: success_gotoへの遷移（確認メッセージ付き）
                                  - 失敗: __end__への遷移（エラーメッセージ付き）

    Note:
        この関数内のinterruptはtry-catchで囲んではいけません。
    """
    logger.info("Google Drive folder ID not set for user. Requesting folder ID via interrupt.")
    interrupt_payload = {
        "type": "missing_drive_folder_id",
        "message": "Google Driveで使う日記フォルダのIDを教えて。\ndrive.google.comのフォルダURLを貼るか、フォルダIDだけを送ってね。",
    }
    user_input = interrupt(interrupt_payload)
    extracted_id = extract_drive_folder_id(str(user_input))

    if not extracted_id:
        logger.info("Failed to extract Drive folder ID from interrupt response. Ending process.")
        failure_message = (
            "フォルダIDを読み取れなかったよ。drive.google.comのフォルダURLかIDを送って、もう一度メッセージを送ってね。"
        )
        return Command(
            goto="__end__",
            update={"messages": [AIMessage(content=failure_message)]},
        )

    user_repository.save_drive_folder_id(userid, extracted_id)
    confirmation = "フォルダIDを登録したわ。次からそのフォルダを使うね。"
    goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
    logger.info("Drive folder ID saved for user. Going to %s.", goto_desc)
    return Command(
        goto=success_goto,
        update={"messages": [AIMessage(content=confirmation)]},
    )
