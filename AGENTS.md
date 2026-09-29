# AGENTS.md

给 Agent / 维护者的仓库工作约定。面向用户的内容一律写 README.md，
这里只记录代码里看不出来的流程与红线。

## 常用命令

```
python eye_care_u.py --test                  # 无界面染色 3 秒自测
.build-venv/Scripts/python tools/menu_qa.py  # 面板 QA：Save 合成点击 + 鼠标穿透 + 更新条回归
python tools/panel_render.py                 # 重新生成 README 面板截图
build.bat                                    # 打包（先托盘 Exit 退出运行中的 exe）
```

## 打包与发布

- `build.bat`：自动创建 `.build-venv` 并装依赖 → 从 `assets/logo.png` 重生成
  多尺寸 `assets/logo.ico` → PyInstaller `--onefile --noconsole` 打包 →
  `probe_icon_resources.py` 校验 exe 图标全尺寸
- 打包前 exe 必须已退出：运行中会锁文件；且 taskkill 硬杀会跳过色彩恢复，
  必须走正常退出路径（托盘 Exit）
- 正式发布走 CI：推送 `v*` tag 触发 `.github/workflows/release.yml` 自动构建
  并发布 Release，配置 SignPath 密钥后同一流水线自动签名；
  本地打包仅用于验证开箱行为（删掉 exe 同目录 settings 文件即模拟新用户）
- **发版前必须把 `eye_care_u.py` 的 `APP_VERSION` 改成与 tag 一致**：
  release.yml 有校验步骤，不一致直接失败（版本号只存在于这一处，
  CI 不做注入）
- **发布后要补 release notes**：CI 的 `--generate-notes` 在无 PR 仓库只生成
  changelog 链接，需 `gh release edit <tag> --notes` 按"本次变化 + 下载"
  格式手写（参照 v1.1.0 / v1.2.0）

## README 截图（docs/panel.png）

- 由 `tools/panel_render.py` 生成，不是手动截图：真实 GlassPanel 按
  SCALE=2.5 重渲染（文字 2.5 倍点阵化、矢量元素整体放大、logo 高清
  重缩放），PrintWindow 采集玻璃底，最后烤 28px 圆角
- 实机渲染分辨率有限（见下节 DPI），截屏后位图拉伸必然发虚，
  禁止用"截屏再放大"替代该工具
- 运行时会 Win+D 最小化全部窗口、以桌面壁纸作亚克力背景，采完自动还原；
  屏幕会短暂闪现面板，属正常
- 玻璃底采的是当前桌面，效果随壁纸变化；想要特定氛围先换壁纸再跑
- README 以 `<p align="center"><img width="440">` 居中展示
  （1100 ÷ 440 = 2.5x 密度），改显示宽度时保持与 SCALE 的整倍数关系
- 面板配色读取 `dist/eye_care_u_settings.json` 当前值，截图展示真实使用状态
- `tools/menu_qa.py` 只写 tools/menu_shot.png 留档，不得写 docs/panel.png

## 实现要点

- **玻璃面板**：`DwmEnableBlurBehindWindow` 配空区域 +
  `DwmExtendFrameIntoClientArea` 的 margins 传 -1 + `SetWindowCompositionAttribute`，
  画布以纯黑为底，DWM 下黑色即玻璃；方案矩阵见 `tools/glass_probe.py`
- **DPI**：exe 未做 DPI 感知。100% 缩放下面板 440×296 物理像素；125% 缩放下
  被 DWM 虚拟化为 550×370（坐标 ×1.25）。自动化定位面板/合成点击时
  要按实际枚举的窗口尺寸换算，不能写死 440×296；
  若未来加 DPI 感知，需同步核对 panel_render 与 menu_qa 的坐标
- **HDR / 10bit**：SetDeviceGammaRamp 不可用，染色失败写 `eye_care_u_error.log`
  （README 已作为已知限制告知用户）
- **退出路径唯一**：面板 Exit 按钮。热键退出已于本次移除——
  RegisterHotKey 路径在实测中未可靠触发，不再恢复
- **新版本感知**：启动 30s 后后台匿名查 GitHub Releases API（24h 节流、
  失败静默、无遥测），结果落 settings 的 `update_*` 三键；提示呈现为
  面板底部更新条（✕ 关当前版本）+ 首次发现时的一次性托盘气泡。
  menu_qa 造 `update_latest=999.0.0` 驱动更新条用例，注意它**不会**点条身
  （会真实打开浏览器）；`--test` 与 QA 不受网络影响（检查延迟 30s 启动）

## 其他

- `assets/logo.png` 是 logo 唯一来源，改动后跑 build.bat 自动重生成
  logo.ico，托盘图标与面板永远同步
- 提交信息：conventional 前缀 + 中文描述（fix / feat / docs / ci / chore…）
