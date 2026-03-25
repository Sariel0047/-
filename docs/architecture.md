# Architecture

## 模块分层

- `main.py`：程序入口
- `qianiu_auto_report/gui.py`：界面层
- `qianiu_auto_report/web_export.py`：网页导出层
- `qianiu_auto_report/data_process.py`：数据处理层
- `qianiu_auto_report/excel_writer.py`：Excel 输出层
- `qianiu_auto_report/config.py`：配置层
- `qianiu_auto_report/utils.py`：通用工具层

## 设计原则

- 单一职责
- 分层清晰
- 便于打包
- 易于扩展
