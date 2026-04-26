# AI 拼音输入习惯学习器方案

## 结论

目前没有找到一个开源项目完整满足“Windows 后台学习用户拼音误输入，并把中文输入法候选词第一/第二位改掉”的需求。可复用的项目分两类：

- [EkaKey-autocorrect-globally](https://github.com/RanvirRox/EkaKey-autocorrect-globally)：接近“全局按键监听 + 纠错学习 + 本地数据库”，但主要面向英文/罗马字，使用 Flutter/Dart + Win32 hook，通过 `SendInput` 回退并重新输入文本，不是 Windows 中文 IME，也不能直接改微软拼音/搜狗拼音候选列表。
- [Rime/librime](https://github.com/rime/librime) + [Rime/weasel 小狼毫](https://github.com/rime/weasel)：接近“真正输入法候选词控制”。Rime 是跨平台输入法引擎，Weasel 是 Windows 前端；Rime 支持词典、权重、拼写运算、容错拼写和用户配置，适合作为第一版底座。

因此推荐第一版不要自研完整 Windows 输入法，也不要尝试从外部进程篡改微软拼音候选窗。更稳的路线是：

1. 安装小狼毫/Rime 作为输入法。
2. 用 Python 写一个本地 sidecar 服务，学习 `错误拼音 -> 正确拼音 -> 最终中文词`。
3. 把学习结果生成 Rime 自定义词库/容错规则，例如把 `xainzai` 映射到 `现在`，并赋高权重。
4. 重新部署 Rime 后，下次输入 `xainzai` 时由 Rime 自己给出 `现在` 候选。

## 为什么不能直接改微软拼音候选词

Windows 现代 IME 应通过 Text Services Framework (TSF) 实现；TSF 是应用和输入法之间的中介，输入法接收输入事件并返回候选/提交文本。微软文档也明确要求现代 IME 使用 TSF，且 IME 在应用容器中会受到权限限制，网络更新和用户学习通常应通过单独桌面进程处理。

外部后台程序可以监听键盘、模拟退格和输入，但通常不能可靠、通用、低风险地修改另一个输入法的候选列表。这样做会遇到候选窗不可控、应用兼容性差、误触密码输入、杀软误报和隐私风险。

## 推荐架构

```text
Rime/Weasel 输入法
  |
  | 输入拼音、候选、提交中文
  v
Python 本地学习服务
  - 默认持久化纠错片段；完整键盘日志作为高级学习数据源分级处理
  - Ollama/其他本地模型默认可分析完整键盘日志；云端/中转模型是否接收完整日志由用户选择
  - SQLite 存储 typo/correction/word/frequency
  - AI 渠道抽象：OpenAI 兼容接口、DeepSeek/Qwen 等中转站、Ollama 本地模型
  - 批量分析用户习惯：字母交换、漏字母、多打字母、音节切分错误
  |
  v
Rime 自定义词库/规则生成器
  - ai_typo.dict.yaml
  - ai_typo.custom.yaml
  - 自定义权重和容错拼写
```

## 第一版 MVP

目标不是“监听所有键入”，而是先做一个可用、低风险、能验证核心价值的版本：

- 使用小狼毫/Rime 作为输入法。
- Python + uv 项目。
- SQLite 表：
  - `events`: 原始纠错事件，字段包括 `wrong_pinyin`, `correct_pinyin`, `committed_text`, `source`, `created_at`。
  - `rules`: 聚合后的习惯规则，字段包括 `wrong`, `correct`, `text`, `weight`, `confidence`, `count`。
  - `providers`: AI 渠道配置，不明文保存密钥，优先使用环境变量。
- 第一阶段可以手动导入样例事件，不急着做全局键盘监听。这里不是永久不做监听，而是先验证 Rime 词库/规则生成这条主链路。
- 第二阶段再接入受控监听：明显托盘图标、暂停热键、密码/浏览器隐私页面规避、应用黑名单、本地优先。
- 生成 Rime 词库后触发重新部署。

## AI 应该做什么

多数 `xainzai -> xianzai -> 现在` 这种模式不需要大模型实时参与，可以本地规则直接识别：

- 相邻字母调换：`ai`/`ia`、`gn`/`ng`
- 漏字母、多字母
- 音节切分错误
- 常见个人偏差统计

AI 更适合离线批处理：

- 把一批纠错事件归纳成“用户习惯规则”。
- 给每条规则打置信度。
- 决定是否应该写入 Rime 词库或仅作为观察数据。

默认建议使用 Ollama 本地模型；本地模型默认可以接收完整键盘日志做习惯分析。云模型或中转模型默认只发送最小化数据，是否发送完整输入日志由用户显式选择。

## 需要安装的软件

第一版 Python + Rime 路线：

- Python 3.11+ 或 3.12
- uv
- 小狼毫/Rime for Windows
- 可选：Ollama
- 可选：OpenAI 兼容 API key，例如 OpenAI、DeepSeek、通义千问兼容网关或自建中转站

如果以后要做真正独立 Windows IME：

- Visual Studio 2022
- Windows SDK
- C++17/C++20
- CMake
- vcpkg 或项目自己的依赖脚本
- TSF/COM 开发知识

## 技术路线选择

### 路线 A：Rime + Python sidecar，推荐

优点：最适合你现在会 Python 和 uv 的情况；能真实影响候选词；开发风险低。

缺点：用户需要安装并使用小狼毫/Rime，而不是微软拼音。

### 路线 B：改造 EkaKey，不推荐作为主线

优点：已有全局监听、纠错学习、SQLite、Windows hook 和 UI。

缺点：技术栈不是 Python；面向英文纠错；修正方式是模拟按键替换文本，不是中文 IME 候选词控制。

### 路线 C：fork Weasel/librime，中后期路线

优点：最接近真正产品化输入法。

缺点：C++/TSF/COM 门槛高，不适合作为第一步。

### 路线 D：从 Microsoft SampleIME 自研，不建议第一步

优点：Windows TSF 正统入口。

缺点：要自己做拼音切分、词典、候选排序、UI、安装注册、兼容性和安全策略，工作量最大。

## 下一步实现计划

1. 初始化 Python/uv 项目：CLI + SQLite + 配置文件。
2. 做“样例事件导入”和“规则聚合”。
3. 生成 Rime 自定义词库文件。
4. 写一个 `xainzai -> xianzai -> 现在` 的端到端测试。
5. 接入 AI provider 抽象，先支持 OpenAI 兼容接口和 Ollama。
6. 再考虑受控键盘监听，不做隐形全局键盘记录。

## 参考资料

- EkaKey: <https://github.com/RanvirRox/EkaKey-autocorrect-globally>
- Rime/librime: <https://github.com/rime/librime>
- Rime/weasel: <https://github.com/rime/weasel>
- Microsoft IME requirements: <https://learn.microsoft.com/en-us/windows/apps/develop/input/input-method-editor-requirements>
- Microsoft Sample IME mirror: <https://github.com/nathancorvussolis/tsf-sample-ime>
- Rime dict.yaml 说明: <https://rimeinn.github.io/rime/dict.html>
- Rime 拼写运算说明: <https://rimeinn.github.io/rime/spelling-algebra.html>
- Microsoft Research 拼音纠错论文页: <https://www.microsoft.com/en-us/research/publication/spelling-correction-in-pinyin-input/>
