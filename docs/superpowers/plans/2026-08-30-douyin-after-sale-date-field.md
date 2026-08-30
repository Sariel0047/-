# 抖音售后日期字段点击修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让抖店售后工作台在选择“完结时间”前先点击 `.aurora-select-content` 外层容器。

**Architecture:** 在现有日期复合控件选择器中加入 `.aurora-select-content` 优先候选，保留 `.auxo-select-selector` 回退。日期范围和导出流程保持原有调用链。

**Tech Stack:** Python 3.10+, Selenium, pytest.

---

### Task 1: Add the regression test

**Files:**
- Modify: `tests/test_web_export_status.py` (`_AfterSaleShortcutDriver` and the date-field regression test)

- [x] **Step 1: Make the fake dropdown open only after clicking `.aurora-select-content`.**
- [x] **Step 2: Run the focused test and verify it fails because the dropdown does not open.**

Run: `.venv-arm64/bin/pytest tests/test_web_export_status.py::test_select_douyin_after_sale_date_field_uses_compact_date_control -q`

Expected before the fix: `1 failed` with the selector returning `False`.

### Task 2: Implement the selector fallback

**Files:**
- Modify: `qianiu_auto_report/web_export.py` (`_select_douyin_after_sale_date_field_option()`)

- [x] **Step 1: Add a date-control XPath for `.aurora-select-content` before the existing selector XPath.**
- [x] **Step 2: Keep existing visible-option lookup and selected-value verification unchanged.**
- [x] **Step 3: Run the focused test and verify the outer-container-then-option click order.**

Run: `.venv-arm64/bin/pytest tests/test_web_export_status.py::test_select_douyin_after_sale_date_field_uses_compact_date_control -q`

Expected: `1 passed`.

### Task 3: Run targeted regression coverage

**Files:**
- Test: `tests/test_web_export_status.py`

- [x] **Step 1: Run all tests covering the Douyin after-sale flow.**

Run: `.venv-arm64/bin/pytest tests/test_web_export_status.py -k 'after_sale' -q`

Expected: all selected tests pass with zero failures.

- [x] **Step 2: Check the final diff and whitespace.**

Run: `git diff --check && git diff -- qianiu_auto_report/web_export.py tests/test_web_export_status.py`

Expected: no whitespace errors and only the requested selector/test changes.
