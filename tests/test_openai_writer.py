"""OpenAICompatWriter against a tiny fake server on localhost (no model needed)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from verdict.engine.llm import LLMError, OpenAICompatWriter


class FakeServer:
    def __init__(self, reply="```sql\nSELECT 1\n```", fail=False):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200 if self.path == "/v1/models" else 404)
                self.end_headers()
                self.wfile.write(b'{"data": []}')

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((self.path, body, self.headers.get("Authorization")))
                if fail:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"model crashed")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(
                    {"choices": [{"message": {"role": "assistant", "content": reply}}]}
                ).encode())

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.close()


def test_writes_n_replies(server):
    w = OpenAICompatWriter(server.url + "/", "verdict-qwen", temperature=0.7)
    replies = w.write("the prompt", 4)
    assert replies == ["```sql\nSELECT 1\n```"] * 4
    assert len(server.requests) == 4
    path, body, auth = server.requests[0]
    assert path == "/v1/chat/completions"
    assert body["model"] == "verdict-qwen" and body["temperature"] == 0.7
    assert body["messages"] == [{"role": "user", "content": "the prompt"}]
    assert auth is None


def test_system_prompt_and_key(server):
    OpenAICompatWriter(server.url, "m", system_prompt="sys", api_key="k").write("p", 1)
    _, body, auth = server.requests[0]
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert auth == "Bearer k"


def test_reachable(server):
    assert OpenAICompatWriter(server.url, "m").reachable()


def test_unreachable_server():
    w = OpenAICompatWriter("http://127.0.0.1:9/v1", "m", timeout_s=1)
    assert not w.reachable(timeout_s=0.5)
    with pytest.raises(LLMError, match="calls to"):
        w.write("p", 2)


def test_server_errors_raise():
    s = FakeServer(fail=True)
    try:
        with pytest.raises(LLMError, match="HTTP 500"):
            OpenAICompatWriter(s.url, "m").write("p", 3)
    finally:
        s.close()
