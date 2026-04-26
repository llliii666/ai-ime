# AI IME

AI IME 是一个面向 Windows + Rime/小狼毫的个人拼音纠错学习助手。它在后台观察用户的拼音误输入和修正过程，把稳定出现的错误习惯沉淀成本地规则，并写入 Rime 词典，让下一次误输入也能优先出现正确候选词。

当前状态：Alpha 原型。项目已经具备托盘程序、设置界面、Rime 写入、手动纠错、自动学习、模型通道配置和本地测试；发布安装包仍在规划中。

## 功能

- Windows 通知区域托盘程序，运行后在后台监听。
- 本地 WebView 设置中心，支持模型、隐私、Rime、开机启动等配置。
- 自动识别常见纠错链路：`错误拼音 -> 删除 -> 正确拼音 -> 空格/回车/数字候选键`。
- 支持手动录入纠错：错误拼音、正确拼音、对应中文。
- 支持 OpenAI 兼容接口、中转站、Ollama、本地 mock provider。
- 支持把规则部署到小狼毫 Rime 用户目录，并尝试触发重新部署。
- AI 分析按自适应间隔批处理，避免每次输入都调用模型。

## 快速开始

要求：

- Windows 10/11。
- 已安装 [uv](https://docs.astral.sh/uv/)。
- 建议先安装小狼毫/Rime，并确认输入法本身可用。

```powershell
git clone <your-repo-url>
cd ai-ime
uv sync
Copy-Item .env.example .env
uv run python -m ai_ime setup
uv run python run.py
```

也可以使用启动脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

启动后，Windows 右下角通知区域会出现 `AI IME` 图标。点击图标打开设置中心。

更详细步骤见 [Windows 快速启动](docs/quickstart-windows.md)。

## 开发命令

```powershell
uv run python -m ai_ime --help
uv run python -m ai_ime setup --dry-run
uv run python -m ai_ime doctor
uv run python run.py
uv run python run.py --status
uv run python run.py --stop
uv run python -m unittest discover -s tests
uv build --no-sources
```

因为本仓库路径可能包含中文或空格，调试 console script 时可使用：

```powershell
uv run --no-editable ai-ime --help
uv run --no-editable ai-ime-start --status
uv run --no-editable ai-ime-tray
```

## 使用验证

自动学习推荐先在记事本中验证：

```text
xainzai -> 删除 -> xianzai -> 空格
```

如果当前应用能通过 Windows UI Automation 暴露文本内容，AI IME 会读取提交后的中文并记录规则。也可以在设置中心的“纠错”页面手动录入：

```text
错误拼音：xainzai
正确拼音：xianzai
对应中文：现在
```

随后检查：

```powershell
uv run python -m ai_ime list-events
uv run python -m ai_ime list-rules
```

## 隐私

这个项目会处理键盘输入数据，默认只在本机工作。完整键盘日志是否记录、是否上传给云端/中转模型，由设置中心控制。Ollama 等本地模型可使用完整日志作为上下文；OpenAI 兼容接口默认不发送完整日志，除非用户明确开启。

发布前请完整阅读 [隐私说明](docs/privacy.md)。

## 架构

核心模块：

- `ai_ime/tray.py`：托盘进程和后台监听生命周期。
- `ai_ime/settings_window.py`、`ai_ime/ui/`：本地 WebView 设置中心。
- `ai_ime/correction/`：按键序列归一化和纠错检测。
- `ai_ime/learning.py`：纠错事件落库、规则聚合、Rime 自动部署。
- `ai_ime/analysis_scheduler.py`：自适应 AI 分析调度。
- `ai_ime/providers/`：模型供应商适配层。
- `ai_ime/rime/`：Rime 文件生成、部署、回滚、小狼毫 redeploy。

更多说明见 [架构文档](docs/architecture.md)。

## 打包与发布

当前建议路线：

1. GitHub 源码预览版：用户使用 `uv` 运行。
2. Alpha zip：使用 PyInstaller 产出 Windows one-folder 包。
3. 正式 Release：安装器、二进制签名、卸载清理、自动更新。

发布流程见 [Release 指南](docs/release.md)。

## 贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。提交 PR 前至少运行：

```powershell
uv run python -m unittest discover -s tests
uv build --no-sources
```

## License

MIT License. See [LICENSE](LICENSE).
