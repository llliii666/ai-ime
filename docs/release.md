# Release 指南

当前项目处于 Alpha。发布路线分为三个阶段。

## 阶段 1：源码预览版

目标用户：开发者、愿意安装 `uv` 的早期试用者。

最低要求：

- README 第一屏说清楚产品是什么、依赖什么、怎么启动。
- 根目录必须保留 `START_HERE.cmd`，让下载 zip 的用户不用理解 Python 包结构。
- `scripts/bootstrap.ps1` 必须能完成依赖安装、初始化、桌面快捷方式创建和启动。
- 没有安装小狼毫或雾凇拼音时必须给出中文提示，而不是隐含失败。

发布前检查：

```powershell
uv run python -m unittest discover -s tests
uv run python -m ai_ime.settings_window --smoke
uv build --no-sources
```

GitHub Release 附件：

- 源码自动归档。
- wheel 和 sdist。
- README 中明确说明当前仍需要用户安装 `uv`、Python、小狼毫/Rime 和雾凇拼音。

## 阶段 2：Alpha zip

目标用户：愿意下载压缩包运行的 Windows 用户。

构建命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-release.ps1 -Version v0.1.0
```

默认采用 PyInstaller one-folder 包。这个阶段仍建议要求用户自行安装小狼毫/Rime 和雾凇拼音。

仓库已提供 `.github/workflows/release.yml`：

- 手动触发 `Release` workflow 可以生成 Windows zip artifact。
- 推送 `v*` tag 时会创建 GitHub Release 并上传 zip、wheel、sdist。

## 阶段 3：正式安装器

目标用户：普通 Windows 用户。

正式安装器还需要补齐：

- 安装器选型：Inno Setup、WiX Toolset 或 MSIX。
- 安装目录选择。
- 开始菜单和桌面快捷方式。
- 开机启动配置。
- 卸载器。
- 卸载时保留或删除用户数据的选项。
- 小狼毫缺失时的下载/安装引导。
- 二进制签名。
- Release notes 和版本迁移说明。
- 可选自动更新。

## Release 检查清单

- CI 通过。
- 本地 Windows 真机验证托盘、设置窗口、Rime 部署、回滚。
- `.env`、数据库、键盘日志没有被打包进发布产物。
- README 快速启动步骤可以从空环境复现。
- 隐私说明与实际默认设置一致。
- 如果更改数据库 schema，提供迁移和回滚说明。
