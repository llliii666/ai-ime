# Contributing

感谢参与 AI IME。这个项目处理键盘输入和输入法配置，贡献时请优先考虑可验证性、隐私边界和回滚能力。

## 本地开发

```powershell
uv sync
uv run python -m ai_ime setup --dry-run
uv run python -m unittest discover -s tests
```

启动托盘：

```powershell
uv run python run.py
```

前台调试：

```powershell
uv run --no-editable ai-ime-tray
```

## 提交前检查

```powershell
uv run python -m unittest discover -s tests
uv run python -m ai_ime.settings_window --smoke
uv build --no-sources
```

## 代码约定

- 核心检测逻辑放在 `ai_ime/correction/`，不要写进监听器。
- 数据库写入集中在 `ai_ime/db.py` 和业务服务层。
- 新增 provider 必须测试请求 payload 和错误处理。
- 新增 UI 功能必须有后端 API 测试或 smoke 测试。
- 不要提交 `.env`、数据库、键盘日志、Rime 用户数据。

## 隐私要求

- 不在日志中打印 API Key。
- 不在测试 fixture 中写真实 key。
- 新增完整日志上传能力时，必须默认关闭云端上传。
- 涉及键盘记录的变更必须在 PR 中说明用户可见控制项。
