"""Google Drive設定の確認と初期化のためのサービスモジュール。

このモジュールは、character_graphとdiary_workflowの両方で使用される
Google Drive設定の確認ロジックを提供します。
"""

from langchain_core.messages import AIMessage
from langgraph.types import Command, interrupt

from chatbot.database.repositories import UserRepository
from chatbot.utils.config import create_logger
from chatbot.utils.drive_folder import extract_drive_folder_id
from chatbot.utils.google_auth import GoogleDriveOAuthManager

logger = create_logger(__name__)


def ensure_oauth_settings(userid: str, success_goto: str) -> Command[str]:
    """
    Google DriveのOAuth設定の有無を確認し、適切なCommandを返す。

    この関数は、OAuth認証情報の存在確認を行います:
    - OAuth認証情報がない場合はinterruptで認証URLを表示し、ユーザーがOAuth完了後にresumeで再開
    - OAuth認証情報がある場合はsuccess_gotoで指定されたノードへ遷移

    Args:
        userid (str): ユーザーID。
        success_goto (str): OAuth設定が揃った場合に遷移するノード名。

    Returns:
        Command[str]: 次の状態への遷移を表すCommand。
                      - OAuth未設定: interruptで認証URL表示後、success_gotoへの遷移
                      - OAuth設定済み: success_gotoへの遷移

    Note:
        この関数内のinterruptはtry-catchで囲んではいけません。
        interruptは例外メカニズムを利用しているためです。
    """
    logger.info("--- Ensure OAuth Settings ---")

    # DI: CosmosClient から UserRepository を作成
    from chatbot.dependencies import create_user_repository

    user_repository = create_user_repository()
    oauth_manager = GoogleDriveOAuthManager(user_repository)

    # OAuth認証情報のチェック
    credentials = oauth_manager.get_user_credentials(userid)
    if not credentials:
        return _handle_oauth_registration(oauth_manager, userid, success_goto)

    logger.info("OAuth credentials verified for user. Going to %s.", success_goto)
    return Command(goto=success_goto)


def ensure_folder_id_settings(userid: str, success_goto: str | list[str]) -> Command[str | list[str]]:
    """
    Google DriveのフォルダIDの有無を確認し、適切なCommandを返す。

    この関数は、フォルダIDの存在確認を行います:
    - フォルダIDがない場合はinterruptで入力を要求し、登録後にsuccess_gotoへ遷移
    - フォルダIDがある場合はsuccess_gotoで指定されたノードへ遷移

    Args:
        userid (str): ユーザーID。
        success_goto (str | list[str]): フォルダID設定が揃った場合に遷移するノード名。
                                         文字列または文字列のリスト（並列実行用）。

    Returns:
        Command[str | list[str]]: 次の状態への遷移を表すCommand。
                                  - フォルダID未設定: 登録処理を経てsuccess_gotoへの遷移（登録完了メッセージ付き）
                                  - フォルダID設定済み: success_gotoへの遷移

    Note:
        この関数内のinterruptはtry-catchで囲んではいけません。
        interruptは例外メカニズムを利用しているためです。
    """
    logger.info("--- Ensure Folder ID Settings ---")

    # DI: CosmosClient から UserRepository を作成
    from chatbot.dependencies import create_user_repository

    user_repository = create_user_repository()

    # フォルダIDのチェック
    folder_id = user_repository.fetch_drive_folder_id(userid)
    if folder_id:
        goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
        logger.info("Google Drive folder ID already set for user. Going to %s.", goto_desc)
        return Command(goto=success_goto)

    # フォルダIDが未設定の場合、interruptで入力を要求
    return _handle_folder_id_registration(user_repository, userid, success_goto)


def _handle_oauth_registration(
    oauth_manager: GoogleDriveOAuthManager, userid: str, success_goto: str
) -> Command[str]:
    """
    OAuth認証の登録を処理する。

    interruptを使用してユーザーに認証URLを表示し、
    OAuth完了後にresumeで再開します。

    Args:
        oauth_manager: GoogleDriveOAuthManagerインスタンス
        userid: ユーザーID
        success_goto: 認証成功時の遷移先ノード名

    Returns:
        Command[str]: 認証結果に応じたCommand
                      - 成功: success_gotoへの遷移（確認メッセージ付き）

    Note:
        この関数内のinterruptはtry-catchで囲んではいけません。
    """
    logger.info("Google credentials not found for user. Requesting OAuth via interrupt.")
    # OAuth の state には userid を渡す
    auth_url, _ = oauth_manager.generate_authorization_url(userid)
    interrupt_payload = {
        "type": "missing_oauth_credentials",
        "message": f"""Google Drive へのアクセス許可がまだ設定されていないみたい。
以下のURLから認可してね。
{auth_url}""".strip(),
    }
    interrupt(interrupt_payload)

    # interruptから再開された場合（OAuth完了後）
    confirmation = "Google Driveの認証が完了したわ。"
    logger.info("OAuth completed for user. Going to %s.", success_goto)
    return Command(
        goto=success_goto,
        update={"messages": [AIMessage(content=confirmation)]},
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
