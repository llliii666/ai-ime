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
uv run python -m ai_ime --db .data/ai-ime.db analyze
uv run python -m ai_ime --db .data/ai-ime.db list-rules
uv run python -m ai_ime --db .data/ai-ime.db export-rime --out .data/rime
```

This writes an `ai_typo.dict.yaml` and a schema patch file into the output directory. Review and test those files before copying them into your Rime user data directory.

After review, you can deploy into a Rime user directory:

```powershell
uv run python -m ai_ime --db .data/ai-ime.db deploy-rime --rime-dir "$env:APPDATA\Rime"
```

If an existing schema patch is present, `deploy-rime` writes a `.ai-ime.pending` patch instead of overwriting it unless you pass `--force-schema-patch`.
