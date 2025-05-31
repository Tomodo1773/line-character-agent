import os
import sys

from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-read-currently-playing",
    "app-remote-control",
    "streaming",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-read-playback-position",
    "user-top-read",
    "user-read-recently-played",
    "user-library-modify",
    "user-library-read",
]

if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
    print("環境変数 SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI をセットしてね！")
    sys.exit(1)

sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=",".join(SCOPES),
)

# 認証URLを表示
print("下記URLにアクセスして認証してね！")
print(sp_oauth.get_authorize_url())

# 認証後のリダイレクトURLからcodeを取得して入力
code = input("リダイレクトURLのcodeパラメータを貼り付けてね: ")
token_info = sp_oauth.get_access_token(code)

print("\n==== 取得したリフレッシュトークン ====")
print(token_info["refresh_token"])
print("\nこのリフレッシュトークンをリモートの環境変数 SPOTIFY_REFRESH_TOKEN にセットしてね！")
