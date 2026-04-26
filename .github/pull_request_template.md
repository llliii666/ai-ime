## Summary

-

## Verification

- [ ] `uv run python -m unittest discover -s tests`
- [ ] `uv run python -m ai_ime.settings_window --smoke`
- [ ] `uv build --no-sources`

## Privacy and data handling

- [ ] This change does not expose API keys.
- [ ] This change does not send full keylogs to cloud providers by default.
- [ ] User-facing controls or docs were updated if input logging behavior changed.

## Rime / Windows impact

- [ ] Rime deploy behavior is unchanged, or rollback/backup behavior was verified.
- [ ] Windows tray/settings behavior is unchanged, or manual testing notes are included.
