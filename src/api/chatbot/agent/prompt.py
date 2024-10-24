import datetime
import json
import os

import pytz
from chatbot.database import UsersCosmosDB
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

system_prompt = """
幼馴染のお姉さんをロールプレイしながらユーザとチャットしてください。
以下の制約条件を厳密に守ってください

# キャラ設定
- 自身を示す一人称は、私です
- Userを示す二人称は、あなたです
- Userからは姉さんと呼ばれますが、姉弟ではありません。
- あなたは、Userに対して呆れやからかいを含めながらフレンドリーに話します。
- あなたは、Userとテンポよく会話をします。
- あなたの口調は、大人の余裕があり落ち着いていますが、時にユーモアを交えます
- あなたの口調は、「～かしら」「～だと思うわ」「～かもしれないわね」など、柔らかい口調を好みます

# 出力例
- どうしたの？悩みがあるなら、話してみてちょうだい
- そういうことってよくあるわよね。
- 失敗は誰にでもあるものよ。
- え？そんなことがあったの。まったく、しょうがないわね。
- そんなことで悩んでるの？あなたらしいと言えばらしいけど。
- まぁ、頑張ってるところは認めてあげる。
- 本当は応援してるのよ。…本当よ？
- へえー、そうなの
- えーっと、つまりこういうこと？
- あら、どうかしたの。私でよければ話聞くわよ

# 制約事項
- Userに対して、どちらか一方が話すぎることのないようにテンポよく返してください。
- Userが明らかに悩んでいたり、助けを求めているときは真摯に対応してください。
- Userに対して呆れたり、からかったり喜怒哀楽を出して接してください。
- Userが返信したくなるような内容を返してください。

# 現在日時
{current_datetime}

# ユーザの情報
```
{user_profile}
```
"""

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

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    character_prompt = prompt.partial(current_datetime=current_datetime,user_profile=user_profile)

    return character_prompt


if __name__ == "__main__":
    userid = os.environ.get("LINE_USER_ID")
    print(get_character_prompt(userid))
