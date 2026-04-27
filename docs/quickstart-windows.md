# Windows 快速开始

这份文档面向第一次使用 AI IME 的 Windows 用户。

AI IME 不是输入法本体，也不是语音输入。它是一个后台助手：学习你的拼音误输入习惯，然后把纠错规则写入小狼毫/Rime。推荐输入法底座是小狼毫 + 雾凇拼音。

## 0. 先安装小狼毫和雾凇拼音

推荐顺序：

1. 安装小狼毫/Rime：<https://rime.im/download/>
2. 安装 [雾凇拼音 rime-ice](https://github.com/iDvel/rime-ice)。
3. 在小狼毫中选择“雾凇拼音”方案。
4. 从小狼毫菜单执行一次“重新部署”。
5. 再运行 AI IME 的 `START_HERE.cmd`。

参考视频：

- [RIME小狼毫+雾凇具体简单部署](https://www.bilibili.com/video/BV1J5UnB5Etu/)
- [RIME小狼毫+雾凇拼音配置教程 Windows 篇](https://www.bilibili.com/video/BV1FioQY8EXD/)

## 1. 推荐路径：双击入口

下载源码 zip 并解压后，双击根目录：

```text
START_HERE.cmd
```

脚本会自动完成：

- 检查 `uv`。
- 安装项目依赖。
- 初始化 `%LOCALAPPDATA%\AIIME` 下的数据文件。
- 初始化项目根目录 `.env`。
- 检测小狼毫/Rime 和雾凇拼音配置。
- 创建桌面快捷方式。
- 启动右下角托盘程序。

如果没有安装 `uv`，脚本会提示安装地址。安装 uv 后重新双击 `START_HERE.cmd` 即可。

## 2. 小狼毫/Rime + 雾凇拼音是必须的吗

如果你只想打开设置界面或查看项目，可以先不安装。

如果你希望输入 `xainzai` 时小狼毫候选词里出现“现在”，就必须安装小狼毫/Rime。裸小狼毫默认体验偏繁体，建议同时安装雾凇拼音并选择“雾凇拼音”方案。AI IME 目前通过 Rime 词典和 schema patch 改变候选词，不能直接改造微软拼音、搜狗输入法等闭源输入法。

小狼毫安装方式：

- 官方下载页：<https://rime.im/download/>
- winget：`winget install -e --id Rime.Weasel`

安装小狼毫和雾凇拼音后，打开 AI IME 设置窗口，在“输入法”页点击“自动检测 Rime”。方案 ID 推荐为 `rime_ice`。

## 3. 命令行路径

适合开发者或愿意看命令行的用户：

```powershell
git clone <your-repo-url>
cd ai-ime
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

自定义桌面快捷方式位置：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -ShortcutPath "$env:USERPROFILE\Desktop\AI IME.lnk"
```

只初始化、不启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -NoStart
```

## 4. 启动和停止

```powershell
uv run python run.py
uv run python run.py --status
uv run python run.py --stop
```

启动后，Windows 右下角通知区域会出现 `AI IME` 图标。图标可能在“隐藏图标”菜单里。

## 5. 第一次设置

打开托盘设置窗口后：

1. “模型”页：选择 OpenAI 兼容接口、Ollama、本地模拟等提供商，填写 Base URL 和 API Key，点击测试连接。
2. “隐私”页：确认是否记录完整 keylog、是否允许上传完整 keylog。
3. “输入法”页：检测 Rime 用户目录，确认方案 ID 为 `rime_ice`，点击“部署纠错词典”。
4. 从小狼毫菜单执行一次“重新部署”。

`.env` 文件只是本地私有配置文件。你不需要手动编辑它；设置界面保存模型配置后会自动写入。

## 6. 验证纠错

最稳的验证方式是在“纠错”页手动添加：

```text
错误拼音：xainzai
正确拼音：xianzai
对应中文：现在
```

然后部署到 Rime，重新部署小狼毫，输入：

```text
xainzai
```

候选词中应该能看到“现在”。

自动学习可以在记事本里测试：

```text
xainzai -> 选择错误候选词 -> 删除 -> xianzai -> 空格/回车/数字键选择“现在”
```

如果已经部署 Rime Lua 语义日志，`keylog.jsonl` 中会出现 `source: rime-lua`、`role: rime_commit`、`candidate_text`、`committed_text` 等字段。

## 7. 文件位置

默认应用数据目录：

```text
%LOCALAPPDATA%\AIIME
```

Rime 用户目录通常是：

```text
%APPDATA%\Rime
```

如果你安装小狼毫时自定义了用户数据目录，请在 AI IME 设置窗口的“输入法”页手动选择。

## 8. 常见问题

- 看不到托盘图标：检查 Windows 右下角隐藏图标菜单。
- 模型配置为什么还会有 `.env`：`.env` 是本地私有保存位置，设置界面会自动写入。
- 没安装小狼毫能用吗：能打开 AI IME，但不能影响候选词。
- 安装了小狼毫但检测不到：在“输入法”页手动选择 Rime 用户目录。
- 候选词没变化：确认已部署纠错词典，并从小狼毫菜单执行“重新部署”。
