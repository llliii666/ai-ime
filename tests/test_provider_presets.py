import unittest

from ai_ime.providers.presets import PROVIDER_PRESETS, infer_provider_preset, provider_presets_payload


class ProviderPresetTests(unittest.TestCase):
    def test_presets_cover_common_provider_families(self) -> None:
        preset_ids = {preset.id for preset in PROVIDER_PRESETS}

        self.assertIn("openai", preset_ids)
        self.assertIn("deepseek", preset_ids)
        self.assertIn("openrouter", preset_ids)
        self.assertIn("ollama", preset_ids)

    def test_presets_payload_is_json_ready(self) -> None:
        payload = provider_presets_payload()

        self.assertTrue(all(isinstance(item["label"], str) for item in payload))
        self.assertTrue(all(item["provider"] in {"openai-compatible", "ollama", "mock"} for item in payload))

    def test_infers_preset_from_base_url_without_requiring_default_model(self) -> None:
        self.assertEqual(
            infer_provider_preset("openai-compatible", openai_base_url="https://api.deepseek.com/v1/"),
            "deepseek",
        )
        self.assertEqual(
            infer_provider_preset("openai-compatible", openai_base_url="http://relay.example/v1"),
            "custom",
        )


if __name__ == "__main__":
    unittest.main()
