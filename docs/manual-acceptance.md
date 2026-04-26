# Manual Acceptance Checklist

这份清单用于在 Windows 真机上验证当前 Alpha 功能。

## 1. 初始化和诊断

```powershell
uv sync
uv run python -m ai_ime setup --dry-run
uv run python -m ai_ime setup
uv run python -m ai_ime doctor
```

期望：

- 数据库和设置文件可初始化。
- `.env` 可检测；如果 key 仍是占位值，`doctor` 应显示 WARN。
- Rime 用户目录能自动检测；没有安装 Rime 时显示 WARN 而不是崩溃。

## 2. 托盘和设置窗口

```powershell
uv run python run.py
uv run python run.py --status
```

期望：

- 命令返回后后台进程仍在运行。
- Windows 通知区域出现 `AI IME` 图标。
- 点击图标可打开设置中心。
- 设置保存后重新打开仍保留。

停止：

```powershell
uv run python run.py --stop
```

前台调试：

```powershell
uv run --no-editable ai-ime-tray
```

## 3. 手动纠错闭环

```powershell
uv run --no-editable ai-ime --db .data/acceptance.db init-db
uv run --no-editable ai-ime --db .data/acceptance.db add-event --wrong xainzai --correct xianzai --text 现在
uv run --no-editable ai-ime --db .data/acceptance.db analyze
uv run --no-editable ai-ime --db .data/acceptance.db list-rules
```

期望：

- 至少一条启用规则映射 `xainzai -> xianzai -> 现在`。

## 4. 设置窗口资源 smoke test

```powershell
uv run python -m ai_ime.settings_window --smoke
```

期望：

- 命令返回 0。
- wheel 构建后仍能找到 `settings.html/css/js`。

## 5. Rime 导出和回滚

```powershell
uv run --no-editable ai-ime --db .data/acceptance.db export-rime --out .data/acceptance-rime
uv run --no-editable ai-ime --db .data/acceptance.db deploy-rime --rime-dir .data/acceptance-deploy
uv run --no-editable ai-ime --db .data/acceptance.db rollback-rime --rime-dir .data/acceptance-deploy --backup .data/acceptance-deploy/.ai-ime-backups/<latest-backup>
```

期望：

- 导出目录包含 `ai_typo.dict.yaml`。
- 字典包含 `现在	xainzai`。
- 部署会创建备份。
- 回滚能恢复或移除生成文件。

## 6. 真实小狼毫验证

只在确认生成文件无误后执行：

```powershell
uv run --no-editable ai-ime --db .data/acceptance.db deploy-rime --rime-dir "$env:APPDATA\Rime"
```

然后从小狼毫菜单执行“重新部署”，输入：

```text
xainzai
```

期望：

- `现在` 出现在候选列表中。
- 正常输入 `xianzai` 不受影响。

## 7. 自动学习验证

推荐在记事本中执行：

```text
xainzai -> 删除 -> xianzai -> 空格
```

或用数字键选择候选：

```text
xainzai -> 删除 -> xianzai -> 1
```

期望：

- 如果记事本可被 UI Automation 读取，`learning.log` 写入 learned 记录。
- `list-events` 和 `list-rules` 能看到新规则。
- 如果读取不到中文，日志应记录 skip，而不是生成错误规则。

## 8. 发布前验证

```powershell
uv run python -m unittest discover -s tests
uv run python -m ai_ime.settings_window --smoke
uv build --no-sources
```

期望：

- 所有测试通过。
- 包构建成功。
- `dist` 不应提交到 Git。
