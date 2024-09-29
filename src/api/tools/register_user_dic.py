import json
import os
from pathlib import Path

from chatbot.database import NameCosmosDB
from dotenv import load_dotenv

load_dotenv()

cosmos = NameCosmosDB()


def main(family_name: dict):
    userid = os.environ.get("LINE_USER_ID")
    cosmos.save_names(userid, family_name)


def fetch():
    return cosmos.fetch_names()


if __name__ == "__main__":

    with open(Path(__file__).parent.parent / "tools" / "family_names.json", "r") as file:
        family_names = json.load(file)
        print(family_names)

    for family_name in family_names:
        main(family_name)

    # items = fetch()
    # print(items)
