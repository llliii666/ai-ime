# Release 指南

当前项目处于 Alpha。发布路线分为三个阶段。

## 阶段 1：源码预览版

目标用户：开发者、愿意安装 uv 的早期试用者。

创建公开仓库后，先把 README 中的 `<your-repo-url>` 替换为真实地址。

发布前检查：

```powershell
uv run python -m unittest discover -s tests
uv run python -m ai_ime.settings_window --smoke
uv build --no-sources
```

GitHub Release 附件：

- 源码自动归档。
- wheel 和 sdist。
- 说明当前仍需要用户安装 uv、Python 和小狼毫。

## 阶段 2：Alpha zip

目标用户：愿意下载压缩包运行的 Windows 用户。

建议命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-release.ps1
```

默认采用 PyInstaller one-folder 包。这个阶段仍建议要求用户自行安装小狼毫/Rime。

## 阶段 3：正式安装器

目标用户：普通 Windows 用户。

需要补齐：

- 安装器：Inno Setup、WiX Toolset 或 MSIX 选型。
- 开始菜单快捷方式。
- 开机启动配置。
- 卸载时保留或删除用户数据的选择。
- 二进制签名。
- Release notes 和版本迁移说明。
- 可选自动更新。

## Release 检查清单

- CI 通过。
- 本地 Windows 真机验证托盘、设置窗口、Rime 部署、回滚。
- `.env`、数据库、键盘日志没有被打包进发布产物。
- README 的快速启动步骤可从空环境复现。
- 隐私说明与实际默认设置一致。
- 如果更改数据库 schema，提供迁移和回滚说明。
