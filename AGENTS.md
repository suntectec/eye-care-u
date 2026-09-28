# AGENTS.md

给 Agent / 维护者的仓库工作约定。面向用户的内容一律写 README.md，
这里只记录代码里看不出来的流程与红线。

## 常用命令

```
python eye_care_u.py --test                  # 无界面染色 3 秒自测
.build-venv/Scripts/python tools/menu_qa.py  # 面板 QA：Save 合成点击 + 鼠标穿透回归
python tools/panel_render.py                 # 重新生成 README 面板截图
build.bat                                    # 打包（先退出运行中的 exe，否则锁文件）
```

## README 截图（docs/panel.png）

- 由 `tools/panel_render.py` 生成，不是手动截图：真实 GlassPanel 按
  SCALE=2.5 重渲染（文字 2.5 倍点阵化、矢量元素整体放大、logo 高清
  重缩放），PrintWindow 采集玻璃底，最后烤 28px 圆角
- 实机面板只有 440×296 物理像素（100% DPI 屏），截屏后位图拉伸必然发虚，
  禁止用"截屏再放大"替代该工具
- 运行时会 Win+D 最小化全部窗口、以桌面壁纸作亚克力背景，采完自动还原；
  屏幕会短暂闪现面板，属正常
- 玻璃底采的是当前桌面，效果随壁纸变化；想要特定氛围先换壁纸再跑
- README 以 `<p align="center"><img width="440">` 居中展示
  （1100 ÷ 440 = 2.5x 密度），改显示宽度时保持与 SCALE 的整倍数关系
- 面板配色读取 `dist/eye_care_u_settings.json` 当前值，截图展示真实使用状态
- `tools/menu_qa.py` 只写 tools/menu_shot.png 留档，不得写 docs/panel.png

## 其他

- `assets/logo.png` 是 logo 唯一来源，改动后跑 build.bat 自动重生成
  logo.ico，托盘图标与面板永远同步
- 提交信息：conventional 前缀 + 中文描述（fix / feat / docs / ci / chore…）
