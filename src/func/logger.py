import logging


def create_logger(name: str) -> logging.Logger:
    """ロガーを作成するファクトリー関数。

    ハンドラは追加せず、伝搬も切らない。Azure Functions のワーカーがルートロガーに
    ハンドラを付けており、そこへ伝搬したログが Application Insights
    （OpenTelemetry）に取り込まれるため。

    Args:
        name (str): ロガーの名前（通常は__name__を使用）

    Returns:
        logging.Logger: ロガーインスタンス
    """
    return logging.getLogger(name)


# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ストリームハンドラを追加
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
