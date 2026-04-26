# AI IME

AI IME is an experimental Windows/Rime helper for learning personal pinyin typo habits.

The first milestone is intentionally small: collect correction events, aggregate typo rules, and export Rime dictionary files that can make a mistyped pinyin code produce the intended Chinese candidate.

Example:

```text
xainzai -> xianzai -> 现在
```

## Development

```powershell
uv run python -m ai_ime --help
uv run python -m unittest discover -s tests
```

## MVP Workflow

```powershell
uv run python -m ai_ime --db .data/ai-ime.db init-db
uv run python -m ai_ime --db .data/ai-ime.db add-event --wrong xainzai --correct xianzai --text 现在
uv run python -m ai_ime --db .data/ai-ime.db list-events
uv run python -m ai_ime --db .data/ai-ime.db analyze
uv run python -m ai_ime --db .data/ai-ime.db analyze-ai --provider mock
uv run python -m ai_ime --db .data/ai-ime.db list-rules
uv run python -m ai_ime --db .data/ai-ime.db disable-rule 1
uv run python -m ai_ime --db .data/ai-ime.db enable-rule 1
uv run python -m ai_ime --db .data/ai-ime.db export-rime --out .data/rime
```

This writes an `ai_typo.dict.yaml` and a schema patch file into the output directory. Review and test those files before copying them into your Rime user data directory.

After review, you can deploy into a Rime user directory:

```powershell
uv run python -m ai_ime --db .data/ai-ime.db deploy-rime --rime-dir "$env:APPDATA\Rime"
```

If an existing schema patch is present, `deploy-rime` writes a `.ai-ime.pending` patch instead of overwriting it unless you pass `--force-schema-patch`.

## AI Providers

The AI layer currently uses standard library HTTP calls, so no SDK dependency is required.

Local secrets and provider defaults go in `.env`; use `.env.example` as the template.

Local Ollama:

```powershell
uv run python -m ai_ime --db .data/ai-ime.db analyze-ai --provider ollama --model qwen2.5:7b
```

OpenAI-compatible endpoint or relay:

```powershell
$env:OPENAI_API_KEY = "..."
uv run python -m ai_ime --db .data/ai-ime.db analyze-ai --provider openai-compatible --model gpt-4o-mini --base-url https://api.openai.com/v1
```

Cloud and relay providers should receive only the data you choose to send. The current MVP only sends stored correction events, not a full keyboard log.

## Data Controls

Rules can be disabled before export, deleted, or re-enabled:

```powershell
uv run python -m ai_ime --db .data/ai-ime.db list-rules
uv run python -m ai_ime --db .data/ai-ime.db disable-rule 1
uv run python -m ai_ime --db .data/ai-ime.db delete-rule 1 --yes
```

Correction events can also be cleared:

```powershell
uv run python -m ai_ime --db .data/ai-ime.db clear-events --yes
```
