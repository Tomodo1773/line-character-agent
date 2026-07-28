"""Azure Functions アプリのエントリポイント。

Application Insights への OpenTelemetry 送出は host.json の `telemetryMode` と
アプリ設定 `PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY` で有効になるため、ここでの初期化は不要。
"""

import azure.functions as func

import line_gateway
import line_worker

app = func.FunctionApp()
app.register_blueprint(line_gateway.bp)
app.register_blueprint(line_worker.bp)
