from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    provider: str
    base_url: str
    model: str
    description: str


PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="openai",
        label="OpenAI",
        provider="openai-compatible",
        base_url="https://api.openai.com/v1",
        model="gpt-5.4-mini",
        description="官方 OpenAI 兼容 Chat Completions 接口。",
    ),
    ProviderPreset(
        id="openrouter",
        label="OpenRouter",
        provider="openai-compatible",
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-4o-mini",
        description="多模型聚合接口，使用 OpenAI 兼容协议。",
    ),
    ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        provider="openai-compatible",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        description="DeepSeek OpenAI 兼容接口。",
    ),
    ProviderPreset(
        id="moonshot",
        label="Moonshot / Kimi",
        provider="openai-compatible",
        base_url="https://api.moonshot.cn/v1",
        model="moonshot-v1-8k",
        description="Moonshot Kimi OpenAI 兼容接口。",
    ),
    ProviderPreset(
        id="siliconflow",
        label="SiliconFlow",
        provider="openai-compatible",
        base_url="https://api.siliconflow.cn/v1",
        model="Qwen/Qwen2.5-7B-Instruct",
        description="硅基流动 OpenAI 兼容接口。",
    ),
    ProviderPreset(
        id="zhipu",
        label="智谱 GLM",
        provider="openai-compatible",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4-flash",
        description="智谱 GLM OpenAI 兼容接口。",
    ),
    ProviderPreset(
        id="groq",
        label="Groq",
        provider="openai-compatible",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        description="Groq OpenAI 兼容接口。",
    ),
    ProviderPreset(
        id="lmstudio",
        label="LM Studio",
        provider="openai-compatible",
        base_url="http://localhost:1234/v1",
        model="local-model",
        description="LM Studio 本地 OpenAI 兼容服务。",
    ),
    ProviderPreset(
        id="ollama",
        label="Ollama",
        provider="ollama",
        base_url="http://localhost:11434",
        model="qwen2.5:7b",
        description="Ollama 本地模型接口。",
    ),
    ProviderPreset(
        id="mock",
        label="本地模拟",
        provider="mock",
        base_url="",
        model="",
        description="离线开发和测试使用。",
    ),
)


def provider_presets_payload() -> list[dict[str, str]]:
    return [asdict(preset) for preset in PROVIDER_PRESETS]


def infer_provider_preset(provider: str, openai_base_url: str = "", ollama_base_url: str = "") -> str:
    if provider == "mock":
        return "mock"
    base_url = ollama_base_url if provider == "ollama" else openai_base_url
    normalized_base = base_url.rstrip("/")
    for preset in PROVIDER_PRESETS:
        if preset.provider == provider and preset.base_url.rstrip("/") == normalized_base:
            return preset.id
    return "custom"
