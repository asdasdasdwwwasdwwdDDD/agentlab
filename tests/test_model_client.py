"""OpenAI 兼容客户端测试：用本地假端点验证请求/解析/计费，不需要真实 API key。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agentlab.models.openai_compat import OpenAICompatModel

RECEIVED: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server 约定
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        RECEIVED.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        payload = {
            "id": "chatcmpl-test",
            "choices": [{"message": {"role": "assistant", "content": "hello from fake"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # 静音
        return


@pytest.fixture()
def fake_server():
    RECEIVED.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()


def test_chat_completion_roundtrip(fake_server, monkeypatch):
    monkeypatch.setenv("AGENTLAB_PRICE_IN", "2.5")
    monkeypatch.setenv("AGENTLAB_PRICE_OUT", "10")
    client = OpenAICompatModel(model="gpt-4o", base_url=fake_server, api_key="test-key")
    response = client.chat([{"role": "user", "content": "hi"}], temperature=0.2)
    assert response.text == "hello from fake"
    assert response.prompt_tokens == 100 and response.completion_tokens == 20
    assert response.cost_usd == pytest.approx(100 / 1e6 * 2.5 + 20 / 1e6 * 10)
    assert RECEIVED[0]["path"] == "/v1/chat/completions"
    assert RECEIVED[0]["auth"] == "Bearer test-key"
    assert RECEIVED[0]["body"]["temperature"] == 0.2


def test_missing_api_key_is_actionable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAICompatModel(model="gpt-4o", base_url="http://127.0.0.1:1/v1", api_key="")


def test_base_url_from_environment(fake_server, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", fake_server)
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    client = OpenAICompatModel(model="deepseek-chat")
    assert client.chat([{"role": "user", "content": "x"}]).text
    assert RECEIVED[-1]["auth"] == "Bearer env-key"
