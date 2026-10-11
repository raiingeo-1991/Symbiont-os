import json
import unittest
from unittest.mock import MagicMock, patch

from core.llm_openai import OpenAIProvider


class OpenAIProviderTests(unittest.TestCase):
    @staticmethod
    def response(payload, status=200):
        response = MagicMock()
        response.status = status
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        return response

    @patch("core.llm_openai.urllib.request.urlopen")
    def test_openai_compatible_local_server(self, urlopen):
        provider = OpenAIProvider(url="http://127.0.0.1:11434/", model="local-test")

        urlopen.return_value = self.response({"data": [{"id": "local-test"}]})
        self.assertTrue(provider.is_available())
        self.assertEqual(provider.list_models(), ["local-test"])

        urlopen.return_value = self.response(
            {"choices": [{"message": {"content": "Локальный ответ"}}]}
        )
        result = provider.chat([{"role": "user", "content": "Привет"}])
        self.assertEqual(result, "Локальный ответ")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/v1/chat/completions")
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent["model"], "local-test")
        self.assertFalse(sent["stream"])


if __name__ == "__main__":
    unittest.main()
