# Windows 快速启动

这份文档面向第一次 clone 项目的用户，目标是在本机跑起托盘程序并完成一条纠错规则验证。

## 1. 准备环境

安装：

- Windows 10/11。
- uv。
- 小狼毫/Rime。

确认小狼毫能正常输入中文后再接入 AI IME。AI IME 不是输入法本体，而是一个 companion app：它写入 Rime 用户目录中的纠错词典和 schema patch。

## 2. 初始化项目

```powershell
git clone <your-repo-url>
cd ai-ime
uv sync
Copy-Item .env.example .env
uv run python -m ai_ime setup
```

如果只想检查会发生什么：

```powershell
uv run python -m ai_ime setup --dry-run
```

诊断环境：

```powershell
uv run python -m ai_ime doctor
```

`env` 如果显示 WARN，通常是 `.env` 里还没有填写真实模型 key。只验证本地纠错时可以先不配置模型。

## 3. 启动托盘程序

```powershell
uv run python run.py
```

查看或停止：

```powershell
uv run python run.py --status
uv run python run.py --stop
```

如果没看到图标，先检查 Windows 通知区域的隐藏图标菜单。

## 4. 配置模型

打开托盘图标的设置窗口，在“模型”页面选择：

- `接口类型`：默认 OpenAI 兼容，也可切到 Ollama 本地或本地模拟。
- `提供商`：可快速填入 OpenAI、OpenRouter、DeepSeek、Moonshot、SiliconFlow、智谱、Groq、LM Studio 等常见接口；自定义中转商会留空 Base URL，按提示填写。
- `测试连接并获取模型`：连接成功后会显示模型下拉菜单；失败时会显示红色错误原因。
- `本地模拟`：只用于开发和测试。

云端/中转模型默认不会收到完整键盘日志，除非在“隐私”页面开启。

## 5. 验证纠错

推荐在记事本中测试：

```text
xainzai
删除
xianzai
空格
```

如果自动识别失败，可以在设置中心“纠错”页面手动添加：

```text
错误拼音：xainzai
正确拼音：xianzai
对应中文：现在
```

检查记录：

```powershell
uv run python -m ai_ime list-events
uv run python -m ai_ime list-rules
```

也可以在设置中心“记录”页面查看三元组明细，并按时间或拼音排序。

## 6. 部署到小狼毫

设置中心“输入法”页面可以自动检测 Rime 目录并部署纠错词典。命令行也可以执行：

```powershell
uv run python -m ai_ime deploy-rime --rime-dir "$env:APPDATA\Rime"
```

部署后需要小狼毫重新部署一次。如果自动 redeploy 没成功，可手动从小狼毫菜单执行“重新部署”。

## 常见问题

- 某些应用读不到提交后的中文：这是 Windows UI Automation 暴露能力限制，先用记事本验证。
- 托盘图标不显示：查看通知区域隐藏图标，或运行 `uv run --no-editable ai-ime-tray` 前台调试。
- 模型连接失败：确认 `.env` 的 Base URL、模型名和 API Key。
- 输入法候选没变化：确认 Rime schema 是当前正在使用的方案，并重新部署小狼毫。

## 小狼毫语义日志适配

部署 Rime 时，AI IME 现在会额外写入：

- `%APPDATA%\Rime\lua\ai_ime_logger.lua`：Rime 内部 Lua 插件，用来记录候选词上屏事件。
- `%APPDATA%\Rime\<schema>.custom.yaml`：注册 `lua_processor@*ai_ime_logger` 和 `table_translator@ai_typo`。

完成部署后必须执行一次“小狼毫重新部署”。重新部署后，使用小狼毫输入并选择候选词时，`keylog.jsonl` 中应该出现 `source: rime-lua`、`role: rime_commit`、`committed_text`、`candidate_text` 等字段。这样模型可以看到“错误拼音 -> 错误候选 -> 删除 -> 正确拼音 -> 正确候选”的完整语义链路。
