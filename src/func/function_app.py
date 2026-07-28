import azure.functions as func
from dotenv import load_dotenv

# 環境変数を.envファイルから読み込み
load_dotenv()

app = func.FunctionApp()
