## Google Drive OAuth対応について

LINEからの初回メッセージ受信時に、Cosmos DB の `users` コンテナに Google Drive のアクセストークン情報が登録されていない場合、Bot から認可 URL を返信します。

1. `.env` に `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`GOOGLE_OAUTH_REDIRECT_URI` を設定する。
2. ユーザーは返信された認可 URL で OAuth を完了すると、サーバー側の `/auth/google/callback` にリダイレクトされ、トークンが `users` コンテナへ保存されます。
3. 保存完了後、LINE へ「認可完了したから、最初のメッセージ再送して」とプッシュ通知します。以降は各ユーザーのトークンで Drive へアクセスします。

※ トークン保存は `GOOGLE_TOKEN_ENC_KEY`（Fernet鍵、Key Vault経由の環境変数）で暗号化してから `users` コンテナへ保存します。フォルダIDもユーザーごとにチャットから受け取り、同じ `users` コンテナへ保存します。
