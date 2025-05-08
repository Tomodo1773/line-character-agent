import os
from pathlib import Path

from chatbot.database.repositories import UserRepository
from dotenv import load_dotenv

load_dotenv()

cosmos = UserRepository()


def main(profile: dict):
    userid = os.environ.get("LINE_USER_ID")
    cosmos.save_profile(userid, profile)


def fetch():
    return cosmos.fetch_profile()


def read_markdown_file():
    try:
        filepath = Path(__file__).parent / "user_profile.md"
        with open(filepath, "r", encoding="utf-8") as file:
            content = file.read()
            return {"content": content}
    except FileNotFoundError:
        print(f"エラー: {filepath} が見つかりません")
        return {"content": ""}
    except Exception as e:
        print(f"エラー: {e}")
        return {"content": ""}


if __name__ == "__main__":
    profile = read_markdown_file()
    print(profile)
    main(profile)

    # items = fetch()
    # print(items)
