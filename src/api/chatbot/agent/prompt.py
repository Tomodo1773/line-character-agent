import datetime
import json
import os

import pytz
from chatbot.database import UsersCosmosDB
from langchain import hub


def read_user_profile(userid: str) -> dict:
    cosmos = UsersCosmosDB()
    result = cosmos.fetch_profile(userid)
    # プロファイルデータを整形
    if isinstance(result, list) and result:
        user_profile = result[0].get("profile", {})
    return json.dumps(user_profile, ensure_ascii=False)


def get_character_prompt(userid: str) -> str:
    user_profile = read_user_profile(userid)
    current_datetime = datetime.datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")

    # プロンプトはLangchain Hubから取得
    # https://smith.langchain.com/hub/tomodo1773/sister_edinet
    prompt = hub.pull("tomodo1773/sister_edinet")
    character_prompt = prompt.partial(current_datetime=current_datetime,user_profile=user_profile)

    return character_prompt


if __name__ == "__main__":
    userid = os.environ.get("LINE_USER_ID")
    print(get_character_prompt(userid))
