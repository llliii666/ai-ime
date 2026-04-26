# AI 输入法项目蓝图（确认稿）

## 1. 项目定位

做一个 Windows 上的 AI 拼音输入习惯学习器。第一阶段不自研完整输入法内核，而是基于小狼毫/Rime 实现“学习用户常见拼音误输入，并让错误拼音也能出现正确中文候选词”的能力。

核心例子：

```text
用户误输入：xainzai
用户修正为：xianzai
最终提交：现在
系统学习：xainzai -> xianzai -> 现在
下次输入：xainzai
候选结果：现在 排在高位
```

## 2. 边界与安全原则

这个项目会触及全局键盘输入，必须从一开始按合法、可控、可解释的软件设计。

- 不做隐藏式键盘记录器。
- 日志分级处理：纠错片段是默认持久化数据；完整键盘日志只作为高级学习数据源，必须有明确状态、暂停入口和清除入口。
- 本地模型策略：Ollama 或其他本地模型可以默认接收完整键盘日志，因为数据不离开本机。
- 云端/中转模型策略：是否发送完整键盘日志由用户在设置中显式选择；默认只发送最小化、脱敏后的纠错片段。
- 密码框、浏览器隐私场景、远程桌面、支付软件、密码管理器默认禁用记录。
- AI 分析默认本地优先，Ollama 优先。
- 任何监听功能必须有托盘状态、暂停按钮、热键和日志查看。

## 3. 技术路线结论

### 推荐路线：Rime/Weasel + Python sidecar

原因：

- Rime/Weasel 是真实 Windows 输入法前端，能控制候选词和词库。
- Python sidecar 负责学习、分析、生成配置，不需要第一天进入 C++/TSF。
- uv 能直接管理 Python 项目环境，符合现有能力。
- 后续如需要更深集成，可再 fork Weasel/librime。

### 不推荐第一阶段直接做的事

- 直接修改微软拼音/搜狗拼音候选词：外部进程通常不能可靠、通用地改另一个 IME 的候选窗口。
- 从零写 TSF 输入法：需要 C++、COM、Windows SDK、候选 UI、词典、安装注册和兼容性测试，工作量过大。
- 直接改造 EkaKey 作为主线：它适合借鉴“全局监听 + 学习 + SQLite”，但不是中文 IME 候选词控制底座。

## 4. 产品形态

### MVP 0：离线验证版

目的：先验证 `错误拼音 -> 正确中文候选` 这条主链路是否成立。

功能：

- Python CLI。
- 手动导入样例纠错事件。
- SQLite 保存事件和规则。
- 生成 Rime 自定义词库或拼写规则。
- 提供端到端测试：`xainzai -> 现在`。

不做：

- 全局键盘监听。这里的意思不是永久不做监听，而是第一阶段先不做监听；先证明 Rime 词库/规则生成能把 `xainzai` 推出 `现在` 候选，再进入受控监听阶段。
- 托盘常驻。
- 安装包。
- 自动改第三方输入法。

### MVP 1：Rime 集成版

功能：

- 自动定位 Rime 用户目录。
- 生成 `ai_typo.dict.yaml`、`ai_typo.schema.yaml` 或 patch 文件。
- 备份用户现有配置。
- 提供 `uv run ai-ime deploy-rime` 命令。
- 提供 `uv run ai-ime rollback-rime` 命令。
- 重新部署 Rime。

关键验证：

- 在小狼毫中输入 `xainzai`，候选列表出现 `现在`。
- 输入正常 `xianzai` 不受破坏。

### MVP 2：AI 分析版

功能：

- AI provider 抽象：
  - Ollama 本地模型。
  - OpenAI 官方 API。
  - OpenAI-compatible 中转站。
- 批量把纠错事件总结为结构化规则。
- 使用严格 JSON/Pydantic schema 接收模型输出。
- 人工审核规则后写入 Rime。

### MVP 3：受控监听版

功能：

- Windows 托盘应用。
- 明显开关状态。
- 只保存短期环形缓冲区。
- 识别模式：错误拼音、退格/删除、正确拼音、空格/回车确认。
- 默认不记录中文正文上下文，只记录纠错片段。
- 应用黑名单和暂停热键。

限制：

- 仅靠全局键盘事件很难可靠知道“最终提交的中文词”。
- 真正可靠的最终中文提交信息应尽量从 Rime/输入法层拿，而不是从任意应用文本框读取。

### MVP 4：产品化版

功能：

- 桌面设置界面。
- 规则审核、搜索、启用/禁用。
- 数据导出/清除。
- 安装包。
- 自动更新。
- 崩溃日志本地查看。
- 可选云同步，但默认关闭。

## 5. 模块设计

```text
ai_ime/
  cli.py                 # 命令行入口
  config.py              # 配置加载、路径定位
  db.py                  # SQLite 连接、迁移
  models.py              # Pydantic 数据模型
  correction/
    detector.py          # 纠错事件检测状态机
    normalize.py         # 拼音标准化
    rules.py             # 规则聚合、置信度计算
  providers/
    base.py              # AI provider 协议
    openai_compatible.py # OpenAI 官方与中转站
    ollama.py            # Ollama 本地
    mock.py              # 测试用 provider
  rime/
    paths.py             # Rime 用户目录定位
    generator.py         # YAML/词库生成
    deploy.py            # 备份、写入、重新部署
    rollback.py          # 回滚
  privacy/
    filters.py           # 应用黑名单、敏感窗口过滤
    redaction.py         # 脱敏
  ui/
    tray.py              # 后期托盘入口
    settings.py          # 后期设置界面
tests/
  unit/
  integration/
  fixtures/
```

## 6. 数据模型草案

### correction_events

记录最小纠错事实。

```text
id
wrong_pinyin
correct_pinyin
committed_text
commit_key              # space / enter / number candidate
app_id_hash             # 可选，不存明文应用标题
source                  # manual / rime / listener
created_at
```

### learned_rules

记录已聚合、可部署规则。

```text
id
wrong_pinyin
correct_pinyin
committed_text
confidence
weight
count
enabled
last_seen_at
provider               # rule / ollama / openai-compatible
explanation
```

### provider_configs

不明文保存密钥，优先使用环境变量或系统凭据。

```text
name
type                   # ollama / openai-compatible
base_url
model
api_key_env
enabled
```

## 7. 纠错识别逻辑

第一版规则检测不用 AI：

- 相邻字母交换：`xainzai -> xianzai`
- 漏字母：`xinzai -> xianzai`
- 多字母：`xiaanzai -> xianzai`
- 常见韵母/声母误序：`ai/ia`、`ei/ie`、`gn/ng`
- 编辑距离阈值。

AI 的角色：

- 离线归纳用户习惯。
- 输出置信度、适用范围、是否推荐写入候选。
- 避免实时输入路径依赖网络。

## 8. Rime 集成策略

优先尝试三层方案，按复杂度递增：

1. 自定义词库/短语：为高置信度 `wrong_pinyin -> committed_text` 写入候选。
2. 拼写运算规则：对系统性错误生成 Rime speller algebra，例如某类相邻字母误序。
3. Lua/插件或 Weasel fork：如果前两种无法满足动态候选控制，再进入更深集成。

实现时必须做实验验证：

- Rime 是否接受特定错误拼音作为编码。
- patch 后是否破坏原有输入方案。
- 权重能否稳定把目标词推到第一/第二候选。

## 9. 环境配置流程

### 必需

- Windows 10/11。
- Python 3.11+ 或 3.12。
- uv。
- 小狼毫/Rime。

### 推荐

- Ollama，用于本地模型。
- Git。
- VS Code 或 Cursor。

### 后期可能需要

- PySide6：桌面设置界面和托盘。
- pynput/keyboard/pywin32：受控监听或 Windows API。
- PyInstaller/Nuitka：打包 exe。
- Inno Setup/WiX：安装器。
- Visual Studio 2022 + Windows SDK：如果进入 TSF/Weasel fork。

## 10. UI 设计

### 第一阶段

只做 CLI：

```text
ai-ime add-event --wrong xainzai --correct xianzai --text 现在
ai-ime analyze
ai-ime deploy-rime
ai-ime list-rules
ai-ime rollback-rime
```

### 第二阶段

做 Windows 托盘：

- 当前状态：学习中 / 暂停 / Rime 未配置 / AI 未配置。
- 快捷操作：暂停 30 分钟、立即部署、打开设置、清除数据。
- 通知：新增规则需确认、部署成功、部署失败。

### 第三阶段

设置界面：

- 总览：学习事件数、规则数、最近部署时间。
- 规则表：错误拼音、候选中文、置信度、启用状态。
- AI 渠道：Ollama、OpenAI-compatible、中转站。
- 隐私：黑名单、数据保留周期、导出/清除。
- Rime：用户目录、备份、回滚、重新部署。

## 11. 测试和验证流程

### 单元测试

- 拼音标准化。
- 编辑距离和误输入分类。
- 状态机识别纠错序列。
- AI 输出 schema 校验。
- Rime YAML 生成。

### 集成测试

- SQLite 迁移。
- mock provider 分析事件。
- Rime 文件生成到临时目录。
- 备份与回滚。

### 手动验收

- 安装小狼毫。
- 写入 `xainzai -> 现在` 规则。
- 重新部署 Rime。
- 输入 `xainzai`，候选出现 `现在`。
- 输入 `xianzai`，原本候选不被破坏。
- 关闭规则后，行为恢复。

## 12. Codex 插件、skills、MCP 使用计划

### 当前可用官方插件

| 插件 | 是否建议使用 | 用途 |
| --- | --- | --- |
| Build Web Apps | 条件使用 | 如果后续选择 React/Tauri/Web 设置界面，用于前端架构、UI 构建、React 性能规范、shadcn 组件 |
| Canva | 暂不使用 | 更适合做展示文档、宣传图、演示材料，不适合核心工程实现 |

### 当前应使用的 skills

| skill | 阶段 | 用途 |
| --- | --- | --- |
| plan | 当前 | 形成确认稿、验收标准、风险和阶段计划 |
| parallel-web-search / firecrawl | 研究 | 查 Rime、TSF、Windows 输入、Ollama 等外部资料 |
| openai-docs | AI 接入 | 查 OpenAI 官方 Responses API、structured outputs、Python SDK |
| security-best-practices / security-review | 全程关键节点 | 这个项目涉及键盘输入，必须做隐私和安全审查 |
| build-fix | 实现期 | 处理 uv、打包、类型检查、Windows API 依赖问题 |
| code-review | 每个里程碑 | 发现行为回归、隐私风险、测试缺口 |
| agent-browser | 如果有 Web UI | 自动打开本地 UI、截图、交互测试 |
| build-web-apps:frontend-app-builder | 如果做 Web/Tauri UI | 生成高质量管理界面 |
| build-web-apps:react-best-practices | 如果做 React UI | React/Next 性能与结构规范 |
| build-web-apps:shadcn 或 shadcn | 如果用 shadcn/ui | 组件安装和组合规范 |
| imagegen | 可选 | 图标、品牌视觉、宣传图 |

### 当前可用 MCP

| MCP | 是否建议使用 | 用途 |
| --- | --- | --- |
| openaiDeveloperDocs | 建议 | AI provider 中 OpenAI 官方接入、structured outputs、Responses API |
| Figma | 可选 | 如果要先做高保真 UI 设计或同步设计稿 |
| Vercel | 暂不使用 | 除非后续有 Web 控制台或文档站需要部署 |
| Canva | 暂不使用 | 演示材料、介绍文档、宣传素材 |

### 建议调用的专业子代理

| 子代理 | 时机 | 用途 |
| --- | --- | --- |
| ai-engineer | AI provider 和规则分析设计 | prompt、schema、评估、Ollama/OpenAI 兼容层 |
| security-reviewer | 监听/隐私/上传逻辑前后 | 防止变成不透明 keylogger，检查数据最小化 |
| test-engineer | MVP 测试计划 | 状态机、Rime 生成、回滚、AI mock 测试 |
| designer | 托盘和设置界面前 | 设置界面信息架构 |
| verifier | 里程碑完成前 | 检查验收证据是否足够 |

## 13. 分阶段执行计划

### 阶段 0：确认路线

产物：

- 本蓝图确认。
- 技术路线确认。
- MVP 范围确认。

### 阶段 1：项目骨架

产物：

- uv Python 项目。
- CLI。
- SQLite。
- 基础数据模型。
- 单元测试框架。

### 阶段 2：Rime 生成器

产物：

- Rime 用户目录定位。
- YAML 生成。
- 备份/回滚。
- 临时目录集成测试。

### 阶段 3：AI provider

产物：

- OpenAI-compatible provider。
- Ollama provider。
- mock provider。
- Pydantic structured output。
- 批量分析命令。

### 阶段 4：真实 Rime 手动验收

产物：

- `xainzai -> 现在` 在小狼毫中可用。
- 部署/回滚命令可用。
- 不破坏正常拼音输入。

### 阶段 5：桌面常驻和受控监听

产物：

- 托盘开关。
- 黑名单。
- 环形缓冲区。
- 纠错片段检测。
- 安全审查。

### 阶段 6：打包发布

产物：

- Windows exe。
- 安装器。
- 卸载和数据清理。
- 用户文档。

## 14. 需要你确认的决策

建议默认确认以下方向：

1. 第一版基于小狼毫/Rime，不尝试直接修改微软拼音候选词。
2. 第一阶段只做 CLI + Rime 生成器，暂不做全局监听；全局监听放到主链路验证后实现。
3. AI 渠道第一批支持 Ollama 和 OpenAI-compatible。
4. 隐私策略采用分级模式：本地模型默认可分析完整键盘日志；云端/中转模型是否接收完整日志由用户显式选择，默认最小化发送。
5. 桌面 UI 后置，先完成可验证输入法链路。

如果这些方向确认，下一步就进入“阶段 1：uv Python 项目骨架 + 数据模型 + 测试”。

## 15. 参考资料

- EkaKey-autocorrect-globally: https://github.com/RanvirRox/EkaKey-autocorrect-globally
- Rime/weasel: https://github.com/rime/weasel
- Rime/librime: https://github.com/rime/librime
- Rime dict.yaml 说明: https://rimeinn.github.io/rime/dict.html
- Rime 拼写运算说明: https://rimeinn.github.io/rime/spelling-algebra.html
- Microsoft IME requirements: https://learn.microsoft.com/en-us/windows/apps/develop/input/input-method-editor-requirements
- Microsoft SampleIME mirror: https://github.com/nathancorvussolis/tsf-sample-ime
- Ollama OpenAI compatibility: https://docs.ollama.com/openai
- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
