# Tmall Offline Order Processing Design

## Goal

Replace the current browser-driven Tmall sold-order export window with an offline file-processing workflow that mirrors the existing Douyin order workflow. The user manually exports the Tmall/Taobao "宝贝销售明细报表", selects it in the application, and receives a summarized workbook covering every valid product ID in the file.

This change does not redesign the rest of the application UI. It also does not delete the existing Selenium exporter, so browser automation can be restored or exposed separately later if needed.

## User Workflow

1. Open the application menu and select "天猫订单表处理".
2. Choose one local Tmall/Taobao "宝贝销售明细报表" file.
3. Click "开始处理并生成汇总表".
4. Wait while the file is validated and summarized.
5. Find the generated workbook in the existing desktop output directory or open that directory from the window.

The window no longer asks for product IDs, payment dates, browser startup, or login. All valid product IDs present in the selected file are summarized.

## UI Changes

The existing `OrderExportWindow` entry point remains in place to minimize integration changes, but its visible workflow becomes offline-only.

- Change the application menu label from "已卖出宝贝订单导出" to "天猫订单表处理".
- Change the window title and header to "天猫订单表处理".
- Replace the existing explanatory text with a concise description of importing a Tmall sold-order detail report and summarizing all products.
- Replace the product ID and date fields with one file path field and a "选择文件" button.
- Remove the "打开工作浏览器" and "我已登录，开始导出订单表" actions.
- Add the primary action "开始处理并生成汇总表".
- Retain the output-directory display, "打开目录" action, status text, progress indicator, execution log, and close action.
- Accept `.csv`, `.xlsx`, `.xls`, `.xlsm`, and `.et` in the file picker and request validation.

Because `.xls` and `.et` reading uses `xlrd`, keep the declared application dependencies consistent by adding the existing `requirements.txt` constraint for `xlrd` to `pyproject.toml`. This ensures those formats remain available in installed or packaged builds, not only in the development environment.

The visual styling should continue to follow the existing Tkinter card, color, spacing, and typography conventions. Broader UI modernization is explicitly out of scope.

## Processing Architecture

`OrderExportWindow` becomes a thin offline controller with the same responsibility split already used by `DouyinOrderFileWindow`:

1. The UI validates that a supported local file was selected.
2. A background thread builds the output path.
3. The worker calls `DataProcessor.save_tmall_sold_order_summary(input_path, output_path)` without a `product_ids` argument.
4. `DataProcessor.summarize_tmall_sold_orders` therefore includes every non-empty product ID in the source file.
5. The UI reports success or converts processing exceptions into the existing friendly error format.

No Selenium object is created, and the offline window has no dependency on Chrome, ChromeDriver, remote debugging port 9222, login state, or payment-date controls.

The existing `SoldOrderExporter` and shared browser automation code remain unchanged and unused by this window.

## Input Contract

The input is a Tmall/Taobao "宝贝销售明细报表" in a supported table format. The existing normalized column matching remains authoritative. The file must contain recognizable columns for:

- Order ID: `主订单编号`, `订单编号`, or `订单号`
- Product ID: `商品ID`, `商品id`, `商品Id`, `宝贝ID`, or `宝贝id`
- Quantity: `购买数量`, `数量`, `商品数量`, or `购买件数`
- Paid amount: `买家实付金额`, `实付金额`, `订单金额`, or `买家实付`
- Order status: `订单状态`
- Logistics number: `物流单号`, `运单号`, or `快递单号`

Blank product IDs are ignored. An empty valid file produces an empty summary workbook with the standard headers. Missing required columns produce the existing business-readable validation error naming the missing usage and accepted column names.

## Output Contract

The output file is written to `ExportConfig.DOWNLOAD_DIR` with the name:

`天猫订单汇总_YYYYMMDD_HHMMSS.xlsx`

It retains the existing Tmall summary columns and formatting:

- 商品id
- 订单笔数
- 订单金额
- 仅退款笔数
- 仅退款金额
- 实际发出笔数
- 实际发出金额
- 退货退款笔数
- 退货退款金额
- 实际成交笔数

The existing blank columns after product ID, amount number formats, and column-width formatting remain unchanged.

## Window Lifecycle

The worker continues to run off the Tk main thread, while all widget updates are scheduled onto the main thread.

During processing:

- Disable file selection, start, output-directory, and close buttons.
- Ignore the window-manager close request and update the status to tell the user that processing must finish first.
- Re-enable controls after either success or failure.

This prevents the window from being destroyed while queued Tk callbacks still target its widgets. Once processing is no longer running, the close button and window-manager close action destroy the window normally.

This lifecycle intentionally differs from the current `DouyinOrderFileWindow`, which keeps its close button enabled while work is running. Changing the Douyin window is outside this feature's scope.

## Error Handling

- Reject missing paths and directories before starting the worker.
- Reject unsupported suffixes with a message listing all supported formats.
- Surface missing-column and unreadable-file errors through `friendly_error_message` and the existing technical-error summary.
- Do not create a partially named success result in the UI unless `save_tmall_sold_order_summary` returns successfully.
- Always restore the non-running UI state in the worker's finalization path while the window remains valid.

## Tests

Add focused tests for the offline Tmall window and retain the existing Tmall processor tests.

- Request validation accepts each supported table suffix and rejects missing or unsupported files.
- Project dependency metadata includes `xlrd` so `.xls` and `.et` support is preserved outside the development environment.
- The processing worker calls `save_tmall_sold_order_summary` without a product-ID filter.
- Output naming follows `天猫订单汇总_YYYYMMDD_HHMMSS.xlsx`.
- Running state disables every destructive or conflicting action, including close.
- A close request during processing does not destroy the window.
- Existing processor coverage continues to verify that all product IDs are included when `product_ids` is omitted, required columns are validated, refund categories are computed, and the workbook is formatted.

## Out of Scope

- Redesigning the main application or other feature windows
- Automatically exporting the source report from Tmall/Taobao
- Adding date filters or product-ID filters to the offline window
- Deleting `SoldOrderExporter` or shared Selenium infrastructure
- Combining Tmall and Douyin into a single generalized import window
- Changing existing Tmall aggregation formulas or output columns
