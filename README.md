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
uv run --no-editable ai-ime --help
uv run python run.py
uv run python run.py --status
uv run python run.py --stop
uv run --no-editable ai-ime-start
uv run --no-editable ai-ime-tray
uv run python -m unittest discover -s tests
```

`run.py` and `ai-ime-start` start the Windows notification-area app in the background. `ai-ime-tray` runs the tray app in the current process for debugging. Because this repository is currently under a path with non-ASCII characters, prefer `uv run --no-editable ai-ime...` for console-script entry points.

## MVP Workflow

```powershell
uv run python -m ai_ime --db .data/ai-ime.db init-db
uv run python -m ai_ime --db .data/ai-ime.db doctor
uv run python -m ai_ime --db .data/ai-ime.db add-event --wrong xainzai --correct xianzai --text 现在
uv run python -m ai_ime --db .data/ai-ime.db detect-sequence --sequence "xainzai{backspace*7}xianzai{space}" --text 现在
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

## Controlled Local Key Logging

The first listener is explicit and time-limited. It is not a hidden background service.

```powershell
uv run python -m ai_ime listen --duration 30 --log-file .data/keylog.jsonl --i-understand
```

Use `ctrl+alt+shift+p` to stop early. The listener records local key names to a JSONL file; it does not infer committed Chinese text yet.

To turn a local keylog into a correction event, provide the final committed text:

```powershell
uv run python -m ai_ime --db .data/ai-ime.db detect-log --log-file .data/keylog.jsonl --text 现在
uv run python -m ai_ime clear-keylog --log-file .data/keylog.jsonl --yes
```

## Tray App

Start the local app in the background:

```powershell
uv run python run.py
```

Check or stop the background app:

```powershell
uv run python run.py --status
uv run python run.py --stop
```

If the icon is not immediately visible, check the Windows notification-area overflow menu.

Or use the installed script entry:

```powershell
uv run --no-editable ai-ime-start
```

Run the tray app in the current process for debugging:

```powershell
uv run --no-editable ai-ime-tray
```

The notification-area icon opens the settings window. Current settings include:

- Listener enabled/paused
- Record full local keylog
- Allow sending full keylog
- Start on Windows login
- OpenAI-compatible and Ollama provider settings
- Rime user directory and dictionary settings

The settings window is a local `pywebview` desktop window backed by static HTML/CSS/JS in `ai_ime/ui/`. It does not open a browser tab; the page calls Python bridge methods for saving settings, testing providers, detecting Rime, and deploying the typo dictionary.

The tray app uses Rime/小狼毫 as the IME engine. AI IME is a companion process that learns rules and writes Rime configuration; it is not a fork of 小狼毫 and does not replace 小狼毫's installer.

## Automatic Learning

When the tray listener is enabled, AI IME watches for this correction shape:

```text
wrong-pinyin -> backspace/delete -> correct-pinyin -> space/enter
```

After the confirm key, it reads the focused Windows text control through UI Automation, compares the text before and after commit, and stores a rule only if it can extract newly inserted Chinese text. If focused text cannot be read, the correction is skipped instead of creating a risky rule.

To verify with 小狼毫:

```text
xainzai -> erase it -> xianzai -> space
```

Then check:

```powershell
uv run python -m ai_ime list-events
uv run python -m ai_ime list-rules
```

If automatic deploy is enabled, AI IME writes the updated `ai_typo` dictionary and attempts to run 小狼毫 redeploy. Some applications do not expose focused text through UI Automation; Notepad is the recommended first manual test target.
