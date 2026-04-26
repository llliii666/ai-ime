import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from ai_ime.models import CorrectionEvent
from ai_ime.providers.ollama import OllamaProvider
from ai_ime.providers.openai_compatible import OpenAICompatibleProvider


class RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_GET(self) -> None:
        self.__class__.requests.append({"path": self.path, "payload": None, "headers": dict(self.headers)})
        if self.path == "/v1/models":
            response = {"data": [{"id": "model-b"}, {"id": "model-a"}]}
        elif self.path == "/api/tags":
            response = {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.1:8b"}]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests.append({"path": self.path, "payload": payload, "headers": dict(self.headers)})
        if self.path == "/v1/chat/completions":
            response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "rules": [
                                        {
                                            "wrong_pinyin": "xainzai",
                                            "correct_pinyin": "xianzai",
                                            "committed_text": "现在",
                                            "confidence": 0.82,
                                            "weight": 142000,
                                            "mistake_type": "adjacent_transposition",
                                            "explanation": "test",
                                            "count": 1,
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        else:
            response = {
                "message": {
                    "content": json.dumps(
                        {
                            "rules": [
                                {
                                    "wrong_pinyin": "xainzai",
                                    "correct_pinyin": "xianzai",
                                    "committed_text": "现在",
                                    "confidence": 0.81,
                                    "weight": 141500,
                                    "mistake_type": "adjacent_transposition",
                                    "explanation": "test",
                                    "count": 1,
                                }
                            ]
                        },
                        ensure_ascii=False,
                    )
                }
            }
        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ProviderHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        RecordingHandler.requests = []
        self.server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def test_openai_compatible_provider_posts_chat_completion(self) -> None:
        provider = OpenAICompatibleProvider(model="test-model", base_url=f"{self.base_url}/v1")
        rules = provider.analyze_events([CorrectionEvent("xainzai", "xianzai", "现在")])

        self.assertEqual(rules[0].provider, "openai-compatible")
        self.assertEqual(RecordingHandler.requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(RecordingHandler.requests[0]["payload"]["response_format"], {"type": "json_object"})
        self.assertIn("Return only one JSON object", RecordingHandler.requests[0]["payload"]["messages"][0]["content"])
        self.assertIn('"events"', RecordingHandler.requests[0]["payload"]["messages"][1]["content"])

    def test_openai_compatible_provider_lists_models(self) -> None:
        provider = OpenAICompatibleProvider(model="", base_url=f"{self.base_url}/v1")
        models = provider.list_models()

        self.assertEqual(models, ["model-a", "model-b"])
        self.assertEqual(RecordingHandler.requests[0]["path"], "/v1/models")

    def test_ollama_provider_posts_native_chat(self) -> None:
        provider = OllamaProvider(model="test-model", base_url=self.base_url)
        rules = provider.analyze_events([CorrectionEvent("xainzai", "xianzai", "现在")])

        self.assertEqual(rules[0].provider, "ollama")
        self.assertEqual(RecordingHandler.requests[0]["path"], "/api/chat")
        self.assertEqual(RecordingHandler.requests[0]["payload"]["format"], "json")

    def test_ollama_provider_lists_models(self) -> None:
        provider = OllamaProvider(model="", base_url=self.base_url)
        models = provider.list_models()

        self.assertEqual(models, ["llama3.1:8b", "qwen2.5:7b"])
        self.assertEqual(RecordingHandler.requests[0]["path"], "/api/tags")


if __name__ == "__main__":
    unittest.main()
