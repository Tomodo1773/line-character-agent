"""Google Drive設定の確認と初期化のためのサービスモジュール。

このモジュールは、character_graphとdiary_workflowの両方で使用される
Google Drive設定の確認ロジックを提供します。

ノード構成:
- ensure_oauth_node: OAuth認証の確認（未設定ならinterrupt）
- ensure_drive_folder_node: フォルダIDの確認（未設定ならinterrupt）
"""

from langchain_core.messages import AIMessage
from langgraph.types import Command, interrupt

from chatbot.database.repositories import UserRepository
from chatbot.utils.config import create_logger
from chatbot.utils.drive_folder import extract_drive_folder_id
from chatbot.utils.google_auth import GoogleDriveOAuthManager

logger = create_logger(__name__)

# OAuthコールバック完了時にaresumeで渡すキーワード
OAUTH_COMPLETED_KEYWORD = "__oauth_completed__"


def ensure_oauth(userid: str, success_goto: str | list[str]) -> Command[str | list[str]]:
    """
    OAuth認証情報の存在を確認し、適切なCommandを返す。

    フロー:
    1. credentialsがない場合、interruptで認証URLを返す
    2. OAuthコールバック後にaresumeされると、interruptからOAUTH_COMPLETED_KEYWORDが返される
    3. credentialsを再確認し、あればsuccess_gotoへ遷移

    Args:
        userid (str): ユーザーID。
        success_goto (str | list[str]): 認証済みの場合に遷移するノード名。

    Returns:
        Command[str | list[str]]: 次の状態への遷移を表すCommand。
                                  - OAuth未設定: interruptで中断（認証URL付き）
                                  - OAuth設定済み: success_gotoへの遷移（update含む）
    """
    logger.info("--- Ensure OAuth ---")

    from chatbot.dependencies import create_user_repository

    user_repository = create_user_repository()
    oauth_manager = GoogleDriveOAuthManager(user_repository)

    credentials = oauth_manager.get_user_credentials(userid)
    if not credentials:
        # interruptで中断し、aresumeで再開されると値が返される
        resume_value = _request_oauth_via_interrupt(oauth_manager, userid)

        # aresumeで再開された場合、credentialsを再確認
        credentials = oauth_manager.get_user_credentials(userid)
        if not credentials:
            # まだcredentialsがない場合はエラー
            logger.error("OAuth completed but credentials still not found")
            from langchain_core.messages import AIMessage

            return Command(
                goto="__end__",
                update={"messages": [AIMessage(content="OAuth設定に失敗したみたい。もう一度試してね。")]},
            )

        # OAUTH_COMPLETED_KEYWORDが渡された場合、resume_valueをstateに保存して次のノードへ
        goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
        logger.info("OAuth completed via callback. Going to %s with resume_value.", goto_desc)
        return Command(goto=success_goto, update={"resume_value": resume_value})

    goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
    logger.info("OAuth credentials found. Going to %s.", goto_desc)
    return Command(goto=success_goto)


def ensure_drive_folder(
    userid: str, success_goto: str | list[str], resume_value: str | None = None
) -> Command[str | list[str]]:
    """
    Drive フォルダIDの存在を確認し、適切なCommandを返す。

    OAuthコールバック後にaresumeで特定キーワードが渡された場合は、
    interruptをスキップしてフォルダID入力を要求する。

    Args:
        userid (str): ユーザーID。
        success_goto (str | list[str]): フォルダID設定済みの場合に遷移するノード名。
        resume_value (str | None): aresumeで渡された値。OAuthコールバック完了キーワードの場合は
                                   フォルダID入力をスキップして直接interruptする。

    Returns:
        Command[str | list[str]]: 次の状態への遷移を表すCommand。
                                  - フォルダID未設定: interruptで入力を要求
                                  - フォルダID設定済み: success_gotoへの遷移
    """
    logger.info("--- Ensure Drive Folder ---")

    from chatbot.dependencies import create_user_repository

    user_repository = create_user_repository()

    # フォルダIDが既に設定されているか確認
    folder_id = user_repository.fetch_drive_folder_id(userid)
    if folder_id:
        goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
        logger.info("Google Drive folder ID already set. Going to %s.", goto_desc)
        return Command(goto=success_goto)

    # OAuthコールバック完了キーワードが渡された場合、フォルダID入力を要求
    # 通常のテキストメッセージの場合もフォルダID入力として処理
    return _handle_folder_id_registration(user_repository, userid, success_goto, resume_value)


def _request_oauth_via_interrupt(oauth_manager: GoogleDriveOAuthManager, userid: str) -> str:
    """
    OAuth認証が必要な場合にinterruptを使用して認証URLを返す。

    Args:
        oauth_manager: GoogleDriveOAuthManagerインスタンス
        userid: ユーザーID

    Returns:
        str: aresumeで渡された値（OAUTH_COMPLETED_KEYWORDなど）

    Note:
        interruptが呼ばれると処理が中断され、aresumeで再開されると
        interruptの呼び出し箇所から戻り値として渡された値が返される。
    """
    logger.info("Google credentials not found for user. Generating auth URL.")
    auth_url, _ = oauth_manager.generate_authorization_url(userid)
    message = f"""Google Drive へのアクセス許可がまだ設定されていないみたい。
以下のURLから認可してね。
{auth_url}""".strip()

    interrupt_payload = {
        "type": "missing_oauth",
        "message": message,
    }
    # interruptで中断し、aresumeで再開されると値が返される
    return interrupt(interrupt_payload)


def _handle_folder_id_registration(
    user_repository: UserRepository, userid: str, success_goto: str | list[str], resume_value: str | None = None
) -> Command[str | list[str]]:
    """
    フォルダIDの登録を処理する。

    Args:
        user_repository: UserRepositoryインスタンス
        userid: ユーザーID
        success_goto: 登録成功時の遷移先ノード名
        resume_value: aresumeで渡された値（OAuthコールバック完了キーワードまたはフォルダID）

    Returns:
        Command[str | list[str]]: 登録結果に応じたCommand
    """
    logger.info("Google Drive folder ID not set for user. Requesting folder ID via interrupt.")

    # resume_valueがOAuth完了キーワードの場合、またはNoneの場合はinterruptでフォルダIDを要求
    if resume_value is None or resume_value == OAUTH_COMPLETED_KEYWORD:
        interrupt_payload = {
            "type": "missing_drive_folder_id",
            "message": "Google Driveで使う日記フォルダのIDを教えて。\ndrive.google.comのフォルダURLを貼るか、フォルダIDだけを送ってね。",
        }
        user_input = interrupt(interrupt_payload)
    else:
        # resume_valueがフォルダIDとして渡された場合（ユーザーからの入力）
        user_input = resume_value

    extracted_id = extract_drive_folder_id(str(user_input))

    if not extracted_id:
        logger.info("Failed to extract Drive folder ID from input. Ending process.")
        failure_message = (
            "フォルダIDを読み取れなかったよ。drive.google.comのフォルダURLかIDを送って、もう一度メッセージを送ってね。"
        )
        return Command(
            goto="__end__",
            update={"messages": [AIMessage(content=failure_message)]},
        )

    user_repository.save_drive_folder_id(userid, extracted_id)
    goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
    logger.info("Drive folder ID saved for user. Going to %s.", goto_desc)
    return Command(goto=success_goto)


# 後方互換性のための関数（diary_workflowでも使用）
def ensure_google_settings(userid: str, success_goto: str | list[str]) -> Command[str | list[str]]:
    """
    Google DriveのOAuth設定とフォルダIDの有無を確認し、適切なCommandを返す。

    Note:
        この関数は後方互換性のために残されています。
        新しいコードでは ensure_oauth と ensure_drive_folder を直接使用してください。
    """
    logger.info("--- Ensure Google Settings (Legacy) ---")

    from chatbot.dependencies import create_user_repository

    user_repository = create_user_repository()
    oauth_manager = GoogleDriveOAuthManager(user_repository)

    # OAuth認証情報のチェック
    credentials = oauth_manager.get_user_credentials(userid)
    if not credentials:
        _request_oauth_via_interrupt(oauth_manager, userid)

    # フォルダIDのチェック
    folder_id = user_repository.fetch_drive_folder_id(userid)
    if folder_id:
        goto_desc = success_goto if isinstance(success_goto, str) else f"nodes {success_goto}"
        logger.info("Google Drive folder ID already set for user. Going to %s.", goto_desc)
        return Command(goto=success_goto)

    # フォルダIDが未設定の場合、interruptで入力を要求
    return _handle_folder_id_registration(user_repository, userid, success_goto)
