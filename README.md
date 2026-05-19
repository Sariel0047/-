# qianiu_auto_report

基于 Python、Selenium、pandas、openpyxl、Tkinter 的千牛自动报表项目骨架。

## 目录说明

- `main.py`：程序入口
- `qianiu_auto_report/`：核心业务包
- `tests/`：测试骨架
- `docs/`：项目文档

## 运行方式

```bash
python main.py
```

默认会打开面向非技术用户的 GUI「报表助手」。如果需要使用旧的命令行自动执行流程：

```bash
python main.py --cli
```

GUI 点击 `开始生成` 时只会唤起一个带 9222 调试端口的工作浏览器。用户自行选择淘宝或抖音页面并登录后，再回到 GUI 点击 `我已登录，开始生成报表`。报表完成后，GUI 会继续等待用户切换店铺或账号后再次点击生成。

## 打包说明

后续可使用 `PyInstaller` 配合 `qianiu_auto_report.spec` 进行打包。
