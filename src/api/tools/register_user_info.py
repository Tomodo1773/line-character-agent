import json
import os
from pathlib import Path

from chatbot.database import UsersCosmosDB
from dotenv import load_dotenv

load_dotenv()

cosmos = UsersCosmosDB()


def main(profile: dict):
    userid = os.environ.get("LINE_USER_ID")
    cosmos.save_profile(userid, profile)


def fetch():
    return cosmos.fetch_profile()


if __name__ == "__main__":

    with open(Path(__file__).parent.parent / "tools" / "user_profile.json", "r") as file:
        profile = json.load(file)
        print(profile)


    main(profile)

    # items = fetch()
    # print(items)
