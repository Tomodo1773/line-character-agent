from dotenv import load_dotenv

from .core import CosmosCore

# .envファイルを読み込む
load_dotenv()


class UsersCosmosDB:

    def __init__(self):
        self.container = CosmosCore("USERS")

    def save_profile(self, userid: str, profile: dict) -> None:
        # 保存するデータを作成
        data = {
            "userid": userid,
            "profile": profile,
        }
        # CosmosDBにデータを保存
        self.container.save(data)

    def fetch_profile(self, userid: str) -> dict:
        query = "SELECT c.profile FROM c WHERE c.userid = @userid"
        parameters = [{"name": "@userid", "value": userid}]
        items = self.container.fetch(query=query, parameters=parameters)
        return items
