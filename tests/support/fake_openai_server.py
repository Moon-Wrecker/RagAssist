"""A tiny in-process OpenAI-compatible HTTP server (stdlib only) for adapter tests.

Why not ``respx``? The installed OpenAI SDK sits on ``httpx2``, which respx cannot patch. A real
socket on loopback exercises the genuine SDK -> HTTP -> JSON path with no coupling to SDK internals,
and it is also what an Ollama / vLLM endpoint looks like from the adapter's point of view.

Supports ``POST /v1/embeddings`` with deterministic vectors, request recording, scripted failures
and artificial latency.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from fakes.embeddings import vector_for


@dataclass
class RecordedRequest:
    path: str
    headers: dict[str, str]
    body: dict[str, Any]


@dataclass
class FakeOpenAIServer:
    default_dimension: int = 8
    requests: list[RecordedRequest] = field(default_factory=list)
    delay_seconds: float = 0.0
    _failures: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None

    # -- lifecycle ------------------------------------------------------------------------------
    def start(self) -> FakeOpenAIServer:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence
                return

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                owner.requests.append(
                    RecordedRequest(
                        path=self.path,
                        headers={k.lower(): v for k, v in self.headers.items()},
                        body=body,
                    )
                )
                if owner.delay_seconds:
                    time.sleep(owner.delay_seconds)
                if owner._failures:
                    status, payload = owner._failures.pop(0)
                    self._send(status, payload)
                    return
                if self.path.rstrip("/").endswith("/embeddings"):
                    self._send(200, owner._embeddings(body))
                else:
                    self._send(404, {"error": {"message": f"no route {self.path}"}})

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):  # client gave up (timeout tests)
                    pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    @property
    def base_url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    # -- scripting ------------------------------------------------------------------------------
    def fail_next(self, status: int = 500, message: str = "boom") -> None:
        self._failures.append((status, {"error": {"message": message, "type": "test_error"}}))

    def reset(self) -> None:
        self.requests.clear()
        self._failures.clear()
        self.delay_seconds = 0.0

    # -- behaviour ------------------------------------------------------------------------------
    def _embeddings(self, body: dict[str, Any]) -> dict[str, Any]:
        raw = body.get("input", [])
        items = raw if isinstance(raw, list) else [raw]
        dimension = int(body.get("dimensions") or self.default_dimension)
        return {
            "object": "list",
            "model": body.get("model", "fake"),
            "usage": {"prompt_tokens": len(items), "total_tokens": len(items)},
            "data": [
                {
                    "object": "embedding",
                    "index": i,
                    "embedding": vector_for(json.dumps(item, sort_keys=True), dimension),
                }
                for i, item in enumerate(items)
            ],
        }

    @property
    def embedding_requests(self) -> list[RecordedRequest]:
        return [r for r in self.requests if r.path.rstrip("/").endswith("/embeddings")]

    def batch_sizes(self) -> list[int]:
        return [
            len(r.body["input"]) if isinstance(r.body["input"], list) else 1
            for r in self.embedding_requests
        ]
