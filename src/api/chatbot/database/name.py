from dotenv import load_dotenv

from .core import CosmosCore

# .envファイルを読み込む
load_dotenv()


class NameCosmosDB:

    def __init__(self):
        self.container = CosmosCore("NAMES")

    def save_names(self, userid: str, name_info: dict) -> None:
        # 保存するデータを作成
        data = {
            "userid": userid,
            "content": name_info,
        }
        # CosmosDBにデータを保存
        self.container.save(data)

    def fetch_names(self):
        query = "SELECT c.content FROM c"
        items = self.container.fetch(query=query, parameters=[])
        return items
