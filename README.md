# Eye Care U

<p align="center">
  <img src="docs/panel.png" width="440" alt="Eye Care U 控制面板">
</p>

Windows 托盘常驻护眼工具：改写显卡驱动层 Gamma Ramp 给屏幕物理输出染色，
压低黑白对比度。无遮罩窗口、零输入干扰，任何分辨率和多显示器全覆盖，
原理与 f.lux、Windows 夜间模式同层。

## 下载

前往 [Releases](https://github.com/suntectec/eye-care-u/releases/latest) 下载最新版
`eye-care-u.exe`，单文件免安装。

首次运行如弹出"Windows 已保护你的电脑"（SmartScreen），点**更多信息 → 仍要运行**
即可，同一台电脑只会提示一次。

## 功能

- Gamma Ramp 硬件级染色：无遮罩窗口、不拦截任何输入、游戏全屏也可用
- 默认暖琥珀低蓝光配色；Red / Green / Blue / Strength 四通道滑杆实时调色，所见即所得
- 亚克力半透明玻璃控制面板，Win10/11 实测，老系统自动回退纯色深底
- Save 保存设置；Exit 退出并自动恢复原色
- 新版本提醒：每天最多一次匿名检查 GitHub Releases（失败静默不重试），
  发现新版后面板底部出现更新条，点击直达下载页；不需要可点 ✕ 关闭
- 托盘悬停提示
- 多显示器同时生效；周期重刷防止被游戏或其他软件重置

## 使用

双击 `eye-care-u.exe`，启动即自动开染。

- 左键或右键托盘图标弹出玻璃控制面板；点面板外部或 Esc 关闭
- 拖动滑杆实时染色；**Save** 保存设置；**Exit** 退出并恢复原色
- 设置保存在 exe 同目录的 `eye_care_u_settings.json`，按 Save 落盘

## 升级

程序发现新版本时会在面板底部提示，点击直达下载页。下载后**用新 exe 覆盖
原位置的旧文件**再运行，配色设置自动保留（设置跟着目录走：放到新位置运行
会重新生成默认配置）。

## 已知限制

- HDR / 10bit 显示模式下系统不支持 Gamma Ramp，染色会失效并在 exe 同目录写
  `eye_care_u_error.log`；关闭 HDR 即可恢复

## 从源码运行

需要 Python 3.8 或更高版本（带 tkinter）和 pillow：

```
pip install pillow
python eye_care_u.py
```

## 签名政策（Code Signing Policy）

- **构建来源**：Release 的 exe 由 GitHub Actions 从对应 tag 的源码构建
  （工作流公开可查：`.github/workflows/release.yml`），二进制可追溯到源码
- **签名**：通过 [SignPath.io](https://about.signpath.io/) 提交签名请求，
  证书由 [SignPath Foundation](https://signpath.org/) 签发；
  v1.0.1 及更早版本为未签名构建
- **团队角色**：Author / Reviewer / Approver 均为 suntectec（唯一维护者），
  GitHub 与 SignPath 账号均启用双因素认证
- **隐私**：本程序唯一的网络访问是**每天最多一次**匿名请求 GitHub Releases
  接口查询新版本——不带任何用户数据、账号或设备唯一标识，断网或请求失败时
  静默跳过；除此之外不联网、不收集、不上传任何数据。设置仅保存在本机
  exe 同目录的 `eye_care_u_settings.json`

## 许可证

[MIT](LICENSE)
