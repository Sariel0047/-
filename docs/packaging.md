# PyInstaller 打包说明

## 1. 打包前准备

1. 进入项目根目录：

```bash
cd /Users/keyunze/Desktop/千牛自动化/qianniu_autum
```

2. 激活虚拟环境（示例）：

```bash
source venv/bin/activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
pip install pyinstaller
```

4. 先做环境自检（推荐）：

```bash
python check_env.py
```

如果结果中有 `FAIL`，先修复后再继续打包。

5. 根据实际环境检查配置文件：

- `qianiu_auto_report/config.py`
- 重点确认：
  - `ExportConfig.EXPORT_URL`
  - `BrowserConfig.CHROMEDRIVER_PATH`
  - 模板文件是否存在于 `qianiu_auto_report/templates/template.xlsx`

## 2. 打包命令

按要求使用以下命令：

```bash
pyinstaller --onefile --noconsole main.py
```

打包完成后可执行文件位于：

- `dist/main`（macOS / Linux）
- `dist/main.exe`（Windows）

## 3. 分发给非技术人员

1. 将以下内容打包成一个目录发给使用者：
   - `dist/main` 或 `dist/main.exe`
   - `qianiu_auto_report/templates/template.xlsx`
   - `qianiu_auto_report/drivers/chromedriver`（或 `chromedriver.exe`）
2. 提供一份简短“使用说明”文本（双击运行、导出路径、常见错误）。
3. 非技术人员首次使用时只需：
   - 双击可执行文件，进入 GUI「报表助手」
   - 平台不确定时保持 `自动识别`
   - 点击 `开始生成`
   - 在程序唤起的工作浏览器中自行选择淘宝或抖店页面并登录
   - 回到 GUI 点击 `我已登录，开始生成报表`
   - 等待桌面生成报表
   - 如需继续跑另一个店铺或账号，在浏览器里切换登录后再次点击 `我已登录，开始生成报表`
4. 如果出现“导出页面地址未配置”，让维护人员修改 `config.py` 后重新打包。

## 4. 常见问题

- 缺少驱动：检查 `chromedriver` 路径配置。
- 模板不存在：检查 `template.xlsx` 是否在模板目录。
- 无法导出：检查千牛页面元素定位是否与当前版本一致。
- Windows 用户不需要手动启动 9222 Chrome；GUI 会执行 Windows 对应的 Chrome 启动命令并带上 9222 调试端口。
- 调试人员如需保留旧命令行流程，可运行 `python main.py --cli`。
