# Manual Acceptance Checklist

This checklist verifies the current MVP without installing system software or cloning external code.

## 1. Environment

```powershell
uv run --no-editable ai-ime --db .data/ai-ime.db doctor
```

Expected:

- `keyboard` is installed.
- `.env` provider config is detected.
- Rime user data directory is detected, or shown as a warning if Rime is not installed.

## 1.1 Tray App

```powershell
uv run python run.py
```

Expected:

- The command returns after starting a background process.
- An `AI` icon appears in the Windows notification area.
- Keyboard logging starts if the listener is enabled in settings.

For foreground debugging:

```powershell
uv run --no-editable ai-ime-tray
```

Expected:

- An `AI` icon appears in the Windows notification area.
- Clicking the icon opens the AI IME settings window.
- Settings can be saved without crashing.
- Exiting from the tray menu closes the app.

## 2. Rule Learning

```powershell
uv run --no-editable ai-ime --db .data/acceptance.db init-db
uv run --no-editable ai-ime --db .data/acceptance.db add-event --wrong xainzai --correct xianzai --text 现在
uv run --no-editable ai-ime --db .data/acceptance.db analyze
uv run --no-editable ai-ime --db .data/acceptance.db analyze-ai --timeout 120
uv run --no-editable ai-ime --db .data/acceptance.db list-rules
```

Expected:

- At least one enabled rule maps `xainzai -> xianzai -> 现在`.
- The OpenAI-compatible rule uses the model from `.env`.

## 3. Rime Export

```powershell
uv run --no-editable ai-ime --db .data/acceptance.db export-rime --out .data/acceptance-rime
```

Expected:

- `.data/acceptance-rime/ai_typo.dict.yaml` exists.
- The dictionary contains one deduplicated entry for `现在	xainzai`.

## 4. Safe Deploy Dry Run

```powershell
uv run --no-editable ai-ime --db .data/acceptance.db deploy-rime --rime-dir .data/acceptance-deploy
uv run --no-editable ai-ime --db .data/acceptance.db rollback-rime --rime-dir .data/acceptance-deploy --backup .data/acceptance-deploy/.ai-ime-backups/<latest-backup>
```

Expected:

- Deploy writes `ai_typo.dict.yaml`.
- Rollback removes generated files or restores previous files.

## 5. Real Rime Manual Check

Only run this after reviewing the generated files:

```powershell
uv run --no-editable ai-ime --db .data/acceptance.db deploy-rime --rime-dir "$env:APPDATA\Rime"
```

Then redeploy Rime from the 小狼毫 menu and type `xainzai`.

Expected:

- `现在` appears as a candidate.
- Normal `xianzai` input still works.

## 6. Controlled Keylog Flow

```powershell
uv run --no-editable ai-ime listen --duration 10 --log-file .data/keylog.jsonl --i-understand
uv run --no-editable ai-ime --db .data/acceptance.db detect-log --log-file .data/keylog.jsonl --text 现在
uv run --no-editable ai-ime clear-keylog --log-file .data/keylog.jsonl --yes
```

Expected:

- Listener starts visibly and exits after the duration or stop hotkey.
- Keylog can be deleted.
- A correction event is detected only when the log contains a usable correction sequence.
