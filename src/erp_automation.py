from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import Settings
from .models import DownloadResult


def yesterday() -> date:
    return date.today() - timedelta(days=1)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True)
def download_yesterday_completed_orders(settings: Settings) -> DownloadResult:
    return download_completed_orders_for_date(settings, yesterday())


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True)
def download_completed_orders_for_date(settings: Settings, order_date: date) -> DownloadResult:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless, downloads_path=str(settings.download_dir))
        context = browser.new_context(accept_downloads=True, viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.goto(settings.erp_url, wait_until="domcontentloaded")

        _login_if_needed(page, settings)
        _ensure_completed_order_page(page, settings.erp_url)
        _filter_ship_time(page, order_date)
        _start_export_filtered_data(page)
        _open_export_records(page)

        before_download_files = _snapshot_download_files(settings.download_dir)
        try:
            with page.expect_download(timeout=180_000) as download_info:
                _download_latest_export(page)

            download = download_info.value
            suggested_name = download.suggested_filename or f"erp_completed_orders_{order_date:%Y-%m-%d}.xlsx"
            file_path = settings.download_dir / suggested_name
            download.save_as(file_path)
            print(f"ERP download saved: {file_path}")
        except PlaywrightTimeoutError:
            _dump_erp_stage_debug(page, "download_timeout")
            file_path = _wait_for_new_download_file(settings.download_dir, before_download_files, page)
            print(f"ERP download found by directory polling: {file_path}")

        context.close()
        browser.close()
        return DownloadResult(file_path=file_path, order_date=f"{order_date:%Y-%m-%d}")


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True)
def download_erp_cost_file(settings: Settings) -> DownloadResult:
    target_path = (
        Path(settings.erp_cost_file)
        if settings.erp_cost_file
        else settings.download_dir / "latest_erp_cost.xlsx"
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless, downloads_path=str(settings.download_dir))
        context = browser.new_context(accept_downloads=True, viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.goto(settings.erp_url, wait_until="domcontentloaded")

        _login_if_needed(page, settings)
        _ensure_system_product_page(page)
        _start_export_filtered_data(page)
        _open_export_records(page)

        before_download_files = _snapshot_download_files(settings.download_dir)
        try:
            with page.expect_download(timeout=180_000) as download_info:
                _download_latest_export(page)

            download = download_info.value
            if target_path.exists():
                target_path.unlink()
            download.save_as(target_path)
            print(f"ERP cost download saved: {target_path}")
        except PlaywrightTimeoutError:
            _dump_erp_stage_debug(page, "cost_download_timeout")
            found_path = _wait_for_new_download_file(settings.download_dir, before_download_files, page)
            if target_path.exists():
                target_path.unlink()
            found_path.replace(target_path)
            print(f"ERP cost download found by directory polling: {target_path}")

        context.close()
        browser.close()
        return DownloadResult(file_path=target_path, order_date=f"{date.today():%Y-%m-%d}")


def _login_if_needed(page: Page, settings: Settings) -> None:
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1_000)
    if _password_input_count(page) == 0 and not _is_erp_login_page(page):
        return

    _fill_login_inputs(page, settings)
    _accept_login_agreement(page)
    _click_login_button(page)
    page.wait_for_timeout(10_000)

    if _password_input_count(page) > 0 or _is_erp_login_page(page):
        _dump_erp_login_debug(page)
        raise RuntimeError("ERP login did not complete.")


def _password_input_count(page: Page) -> int:
    for _ in range(5):
        try:
            return page.locator("input[type='password']").count()
        except Exception:
            page.wait_for_timeout(1_000)
    return page.locator("input[type='password']").count()


def _is_erp_login_page(page: Page) -> bool:
    return bool(
        page.evaluate(
            """
            () => {
                const text = document.body.innerText || '';
                return text.includes('账号密码登录')
                    || text.includes('手机号登录')
                    || text.includes('我已阅读并同意');
            }
            """
        )
    )


def _fill_login_inputs(page: Page, settings: Settings) -> None:
    fields = [
        ("卖家账号/主账号", settings.erp_seller_account),
        ("账号名/手机号", settings.erp_phone),
        ("密码", settings.erp_password),
    ]
    for placeholder, value in fields:
        locator = page.get_by_placeholder(placeholder)
        if locator.count() > 0:
            locator.fill(value)

    page.evaluate(
        """
        ([sellerAccount, phone, password]) => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const inputs = Array.from(document.querySelectorAll('input'))
                .filter((el) => isVisible(el) && el.type !== 'checkbox' && el.type !== 'hidden');
            const values = [sellerAccount, phone, password];
            const setValue = (el, value) => {
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, value);
                else el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'a' }));
                el.blur();
            };
            inputs.slice(0, 3).forEach((el, index) => setValue(el, values[index]));
        }
        """,
        [settings.erp_seller_account, settings.erp_phone, settings.erp_password],
    )


def _accept_login_agreement(page: Page) -> None:
    page.evaluate(
        """
        () => {
            const checkbox = document.querySelector("input[type='checkbox']");
            const agreementText = Array.from(document.querySelectorAll('label, div, span'))
                .find((el) => (el.innerText || el.textContent || '').includes('我已阅读并同意'));
            if (agreementText) agreementText.click();
            if (!checkbox) return;
            const label = checkbox.closest('label') || checkbox.parentElement;
            if (!checkbox.checked && label) label.click();
            if (!checkbox.checked) {
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked')?.set;
                if (setter) setter.call(checkbox, true);
                else checkbox.checked = true;
                checkbox.dispatchEvent(new Event('input', { bubbles: true }));
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
        """
    )


def _click_login_button(page: Page) -> None:
    clicked = page.evaluate(
        """
        () => {
            const button = Array.from(document.querySelectorAll('button'))
                .find((el) => (el.innerText || el.textContent || '').replace(/\\s/g, '').includes('登录'));
            if (!button) return false;
            button.click();
            return true;
        }
        """
    )
    if not clicked:
        _click_button_or_text(page, "登录")


def _ensure_completed_order_page(page: Page, completed_order_url: str) -> None:
    page.wait_for_timeout(5_000)
    for _ in range(3):
        if _is_completed_order_page(page):
            return

        _force_open_completed_order_url(page, completed_order_url)
        if _is_completed_order_page(page):
            return

        _open_order_module_from_home(page)
        _force_open_completed_order_url(page, completed_order_url)
        if _is_completed_order_page(page):
            return

    if _is_completed_order_page(page):
        return

    _dump_erp_navigation_debug(page)
    raise RuntimeError("Cannot open ERP completed-order page.")


def _force_open_completed_order_url(page: Page, completed_order_url: str) -> None:
    for _ in range(2):
        try:
            page.goto(completed_order_url, wait_until="commit", timeout=15_000)
        except Exception:
            pass
        page.wait_for_timeout(8_000)

        page.evaluate(
            """
            (url) => {
                if (!window.location.href.includes('/app/order/list/t/8')) {
                    window.location.href = url;
                }
                window.location.hash = '/app/order/list/t/8';
                window.dispatchEvent(new HashChangeEvent('hashchange'));
            }
            """,
            completed_order_url,
        )
        page.wait_for_timeout(8_000)


def _is_completed_order_page(page: Page) -> bool:
    return bool(
        page.evaluate(
            """
            () => {
                const href = window.location.href || '';
                const hash = window.location.hash || '';
                const text = document.body.innerText || '';
                const onCompletedRoute = href.includes('/app/order/list/t/8') || hash.includes('/app/order/list/t/8');
                const hasCompletedTab = text.includes('已完结');
                const hasOrderPageSignal = ['平台订单号', '订单管理', '订单状态', '发货时间'].some((item) => text.includes(item));
                const hasActionSignal = ['筛选', '导出', '打印发货单'].some((item) => text.includes(item));
                return (onCompletedRoute && (hasCompletedTab || hasOrderPageSignal || hasActionSignal))
                    || (hasCompletedTab && (hasOrderPageSignal || hasActionSignal));
            }
            """
        )
    )


def _open_order_module_from_home(page: Page) -> None:
    _click_visible_text_by_mouse(page, "订单", left_limit=180)
    page.wait_for_timeout(1_000)
    _click_visible_text_by_mouse(page, "订单管理")
    page.wait_for_timeout(4_000)
    _click_visible_text_by_mouse(page, "已完结")
    page.wait_for_timeout(4_000)


def _ensure_system_product_page(page: Page) -> None:
    page.wait_for_timeout(2_000)
    for _ in range(3):
        if _is_system_product_page(page):
            return

        if not _click_visible_text_by_dom_anywhere(page, "\u5546\u54c1"):
            _click_visible_text_by_mouse(page, "\u5546\u54c1", left_limit=180)
        page.wait_for_timeout(2_000)
        if not _click_visible_text_by_dom_anywhere(page, "\u7cfb\u7edf\u8d27\u54c1"):
            if not _click_visible_text_by_mouse_anywhere(page, "\u7cfb\u7edf\u8d27\u54c1"):
                if page.get_by_text("\u7cfb\u7edf\u8d27\u54c1", exact=True).count() > 0:
                    page.get_by_text("\u7cfb\u7edf\u8d27\u54c1", exact=True).click()
        page.wait_for_timeout(2_000)

        if not _is_system_product_page(page):
            if page.get_by_text("\u7cfb\u7edf\u8d27\u54c1", exact=True).count() > 0:
                page.get_by_text("\u7cfb\u7edf\u8d27\u54c1", exact=True).click()
                page.wait_for_timeout(2_000)

        if _is_system_product_page(page):
            return

    _dump_erp_stage_debug(page, "system_product_navigation_failed")
    raise RuntimeError("Cannot open ERP system product page.")


def _is_system_product_page(page: Page) -> bool:
    return bool(
        page.evaluate(
            """
            () => {
                const text = document.body.innerText || '';
                const href = window.location.href || '';
                const hash = window.location.hash || '';
                const hasProductText = ['系统货品', '货品名称', '成本价', '商品'].some((item) => text.includes(item));
                const hasExport = text.includes('导出');
                const productRoute = /goods|product|sku|item/i.test(`${href} ${hash}`);
                return (hasProductText && hasExport) || (productRoute && hasProductText);
            }
            """
        )
    )


def _click_visible_text_by_mouse(page: Page, text_value: str, left_limit: int | None = None) -> None:
    point = page.evaluate(
        """
        ([textValue, leftLimit]) => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const text = (el) => (el.innerText || el.textContent || '').trim();
            const clickTarget = (el) => {
                const parent = el.closest('a, button, li, [role="button"], .el-menu-item, .el-sub-menu__title, .ant-menu-item, .ant-tabs-tab, .ivu-tabs-tab');
                return parent || el;
            };
            const candidates = Array.from(document.querySelectorAll('a, li, div, span'))
                .filter((el) => {
                    const visibleText = text(el).replace(/\\s/g, '');
                    if (!isVisible(el) || !visibleText.includes(textValue.replace(/\\s/g, ''))) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.width < 260 && rect.height > 0 && rect.height < 120
                        && (leftLimit == null || rect.left < leftLimit);
                })
                .sort((a, b) => {
                    const ar = a.getBoundingClientRect();
                    const br = b.getBoundingClientRect();
                    return (ar.width * ar.height) - (br.width * br.height);
                });
            const target = candidates.map(clickTarget).find(isVisible);
            if (!target) return null;
            const rect = target.getBoundingClientRect();
            return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        }
        """,
        [text_value, left_limit],
    )
    if point:
        page.mouse.click(point["x"], point["y"])


def _filter_ship_time(page: Page, order_date: date) -> None:
    start_time = f"{order_date:%Y-%m-%d} 00:00:00"
    end_time = f"{order_date:%Y-%m-%d} 23:59:59"
    use_yesterday_shortcut = order_date == date.today() - timedelta(days=1)

    _dump_erp_stage_debug(page, "before_date_filter")
    _fill_ship_time_range(page, start_time, end_time, use_yesterday_shortcut=use_yesterday_shortcut)
    _click_button_or_text_anywhere(page, "\u7b5b\u9009")
    page.wait_for_timeout(5_000)
    _dump_erp_stage_debug(page, "after_date_filter")


def _fill_ship_time_range(page: Page, start_time: str, end_time: str, use_yesterday_shortcut: bool = False) -> None:
    if use_yesterday_shortcut and _select_yesterday_shortcut_anywhere(page):
        return

    if _fill_ship_time_picker_anywhere(page, start_time, end_time):
        return

    if _fill_ship_time_inputs_anywhere(page, start_time, end_time):
        return

    if _fill_date_range_picker_popup_anywhere(page, start_time, end_time):
        return

    selectors = [
        ("input[placeholder='发货开始时间']", "xpath=//input[@placeholder='发货开始时间']/following::input[@placeholder='结束时间'][1]"),
        ("xpath=//*[contains(normalize-space(), '发货时间')]/following::input[1]", "xpath=//*[contains(normalize-space(), '发货时间')]/following::input[2]"),
    ]

    for start_selector, end_selector in selectors:
        start_input = page.locator(start_selector)
        end_input = page.locator(end_selector)
        if start_input.count() > 0 and end_input.count() > 0:
            _set_text_input(start_input.first(), start_time)
            _set_text_input(end_input.first(), end_time)
            return

    if _fill_visible_date_range_by_dom(page, start_time, end_time):
        return

    _dump_erp_date_debug(page)
    raise RuntimeError("Cannot find ERP shipment-time date inputs.")


def _fill_ship_time_picker_anywhere(page: Page, start_time: str, end_time: str) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            if _fill_ship_time_picker_scope(scope, start_time, end_time):
                return True
        except Exception:
            continue
    return False


def _select_yesterday_shortcut_anywhere(page: Page) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            if _select_yesterday_shortcut_scope(scope):
                print("ERP selected shipment date via yesterday shortcut")
                return True
        except Exception:
            continue
    return False


def _select_yesterday_shortcut_scope(scope) -> bool:
    if not _open_ship_time_picker(scope):
        return False
    _dump_erp_stage_debug(scope.page, "ship_time_picker_open")
    scope.page.wait_for_timeout(500)

    click_text_script = """
            (targetText) => {
                const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s/g, '');
                const candidates = Array.from(document.querySelectorAll('*'))
                    .filter(isVisible)
                    .filter((el) => textOf(el) === targetText)
                    .sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        const aArea = ar.width * ar.height;
                        const bArea = br.width * br.height;
                        return (aArea - bArea) || (ar.top - br.top) || (ar.left - br.left);
                    });
                if (!candidates[0]) return false;
                candidates[0].click();
                return true;
            }
            """
    clicked = bool(scope.evaluate(click_text_script, "\u6628\u5929"))
    if not clicked:
        clicked = bool(scope.page.evaluate(click_text_script, "\u6628\u5929"))
    if not clicked:
        return False

    scope.page.wait_for_timeout(700)
    return True


def _fill_ship_time_picker_scope(scope, start_time: str, end_time: str) -> bool:
    start_date, start_clock = start_time.split(" ")
    end_date, end_clock = end_time.split(" ")
    if not _open_ship_time_picker(scope):
        return False
    _dump_erp_stage_debug(scope.page, "ship_time_picker_open")

    filled = _fill_ship_time_picker_panel(scope, start_date, start_clock, end_date, end_clock)
    if not filled:
        filled = _fill_ship_time_picker_panel(scope.page, start_date, start_clock, end_date, end_clock)
    scope.page.wait_for_timeout(1_000)

    query_text = _read_scope_body_text(scope)
    if f"{start_time}-{end_time}" in query_text or f"{start_time} - {end_time}" in query_text:
        return True

    start_input = scope.locator("input[placeholder='\u53d1\u8d27\u5f00\u59cb\u65f6\u95f4']")
    if filled and start_input.count() == 0:
        print("ERP accepted filled date picker without legacy shipment-time placeholder")
        return True
    try:
        start_value = start_input.first().input_value(timeout=2_000)
    except Exception:
        start_value = ""
    return bool(filled and start_value == start_time)


def _open_ship_time_picker(scope) -> bool:
    if _open_first_visible_date_range(scope):
        return True

    points = scope.evaluate(
        """
        () => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const startPlaceholder = '\\u53d1\\u8d27\\u5f00\\u59cb\\u65f6\\u95f4';
            const startInput = Array.from(document.querySelectorAll('input'))
                .find((el) => isVisible(el) && (el.getAttribute('placeholder') || '') === startPlaceholder);
            if (!startInput) return [];

            let box = startInput.closest('.el-date-editor, .el-range-editor, .el-input__wrapper, .el-form-item, div');
            const dateEditor = startInput.closest('.el-date-editor, .el-range-editor');
            if (dateEditor) box = dateEditor;
            const target = box || startInput;
            const r = target.getBoundingClientRect();
            const ir = startInput.getBoundingClientRect();
            const y = ir.top + ir.height / 2;
            return [
                { x: ir.left + 10, y },
                { x: ir.left + ir.width / 2, y },
                { x: r.left + 22, y: r.top + r.height / 2 },
                { x: r.left + r.width / 2, y: r.top + r.height / 2 },
                { x: r.right - 22, y: r.top + r.height / 2 },
            ];
        }
        """
    )
    if not points:
        return False

    offset_x = 0
    offset_y = 0
    if scope != scope.page.main_frame:
        frame_box = scope.frame_element().bounding_box()
        if frame_box:
            offset_x = frame_box["x"]
            offset_y = frame_box["y"]

    print(f"ERP ship time click points, frame offset=({offset_x}, {offset_y}), inner={points}")
    for point in points:
        x = point["x"] + offset_x
        y = point["y"] + offset_y
        scope.page.mouse.move(x, y)
        scope.page.mouse.down()
        scope.page.wait_for_timeout(80)
        scope.page.mouse.up()
        scope.page.wait_for_timeout(500)
        if _ship_time_picker_is_open(scope) or _ship_time_picker_is_open(scope.page):
            return True
    return False


def _open_first_visible_date_range(scope) -> bool:
    candidates = [
        "css=.el-date-editor.el-range-editor",
        "css=.el-range-editor",
        "css=.el-date-editor",
        "xpath=(//input[@class='el-range-input' or contains(@class, 'el-range-input')]/ancestor::*[contains(@class, 'el-date-editor') or contains(@class, 'el-range-editor')][1])[1]",
    ]
    for selector in candidates:
        locator = scope.locator(selector)
        count = locator.count()
        for index in range(min(count, 5)):
            item = locator.nth(index)
            try:
                if not item.is_visible():
                    continue
                box = item.bounding_box()
                if not box or box["width"] < 120 or box["height"] < 20:
                    continue
                item.click(position={"x": min(24, box["width"] / 2), "y": box["height"] / 2}, timeout=5_000)
                scope.page.wait_for_timeout(700)
                if _ship_time_picker_is_open(scope) or _ship_time_picker_is_open(scope.page):
                    print(f"ERP opened first visible date range via {selector} index={index} box={box}")
                    return True
            except Exception:
                continue
    return False


def _ship_time_picker_is_open(scope) -> bool:
    try:
        return bool(
            scope.evaluate(
                """
                () => {
                    const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    return Array.from(document.querySelectorAll('.el-date-range-picker, .el-picker-panel, .el-popper, [class*="date-range"], [class*="picker"], [class*="popper"]'))
                        .some((el) => isVisible(el) && el.querySelectorAll('input').length >= 4);
                }
                """
            )
        )
    except Exception:
        return False


def _fill_ship_time_picker_panel(scope, start_date: str, start_clock: str, end_date: str, end_clock: str) -> bool:
    return bool(
        scope.evaluate(
        """
        ([startDate, startClock, endDate, endClock]) => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const rectOf = (el) => el.getBoundingClientRect();
            const panels = Array.from(document.querySelectorAll('.el-date-range-picker, .el-picker-panel, .el-popper, [class*="date-range"], [class*="picker"], [class*="popper"]'))
                .filter((el) => isVisible(el))
                .map((el) => ({
                    el,
                    rect: rectOf(el),
                    inputs: Array.from(el.querySelectorAll('input')).filter(isVisible),
                    text: el.innerText || el.textContent || '',
                }))
                .filter((item) => item.inputs.length >= 2)
                .sort((a, b) => {
                    const aScore = (a.text.includes('今天') || a.text.includes('昨天') || a.text.includes('确定')) ? 1 : 0;
                    const bScore = (b.text.includes('今天') || b.text.includes('昨天') || b.text.includes('确定')) ? 1 : 0;
                    return (bScore - aScore) || (b.inputs.length - a.inputs.length);
                });
            const panel = panels[0]?.el;
            if (!panel) return false;

            const inputs = Array.from(panel.querySelectorAll('input'))
                .filter(isVisible)
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (ar.top - br.top) || (ar.left - br.left);
                })
                .slice(0, 4);
            if (inputs.length < 2) return false;

            const values = inputs.length >= 4
                ? [startDate, startClock, endDate, endClock]
                : [`${startDate} ${startClock}`, `${endDate} ${endClock}`];
            const setValue = (el, value) => {
                el.removeAttribute('readonly');
                el.removeAttribute('disabled');
                el.focus();
                el.select?.();
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, value);
                else el.value = value;
                el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
                el.blur();
            };
            inputs.slice(0, values.length).forEach((el, index) => setValue(el, values[index]));

            const confirmText = '\\u786e\\u5b9a';
            const findConfirm = (root) => Array.from(root.querySelectorAll('button, span, div'))
                .filter(isVisible)
                .filter((el) => (el.innerText || el.textContent || '').trim() === confirmText)
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (br.top - ar.top) || (br.left - ar.left);
                })[0];
            const confirm = findConfirm(panel) || findConfirm(document);
            if (confirm) {
                confirm.click();
            } else {
                inputs[inputs.length - 1].dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
                inputs[inputs.length - 1].dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
            }
            return true;
        }
        """,
        [start_date, start_clock, end_date, end_clock],
        )
    )


def _read_scope_body_text(scope) -> str:
    try:
        return scope.locator("body").inner_text(timeout=2_000)
    except Exception:
        return ""


def _fill_ship_time_inputs_anywhere(page: Page, start_time: str, end_time: str) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            if _fill_ship_time_inputs_scope(scope, start_time, end_time):
                return True
        except Exception:
            continue
    return False


def _fill_ship_time_inputs_scope(scope, start_time: str, end_time: str) -> bool:
    start_input = scope.locator("input[placeholder='\u53d1\u8d27\u5f00\u59cb\u65f6\u95f4']")
    if start_input.count() == 0:
        return False

    end_input = scope.locator(
        "xpath=//input[@placeholder='\u53d1\u8d27\u5f00\u59cb\u65f6\u95f4']"
        "/following::input[@placeholder='\u7ed3\u675f\u65f6\u95f4'][1]"
    )
    if end_input.count() == 0:
        return False

    _human_replace_text(start_input.first(), start_time)
    scope.page.wait_for_timeout(300)
    _human_replace_text(end_input.first(), end_time)
    scope.page.wait_for_timeout(300)
    end_input.first().press("Enter")
    scope.page.wait_for_timeout(800)

    return start_input.first().input_value() == start_time and end_input.first().input_value() == end_time


def _human_replace_text(locator: Locator, value: str) -> None:
    locator.click()
    locator.press("Control+A")
    locator.press("Backspace")
    locator.type(value, delay=20)
    locator.press("Tab")


def _fill_date_range_picker_popup_anywhere(page: Page, start_time: str, end_time: str) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            if _fill_date_range_picker_popup_scope(scope, start_time, end_time):
                return True
        except Exception:
            continue
    return False


def _fill_date_range_picker_popup_scope(scope, start_time: str, end_time: str) -> bool:
    start_date, start_clock = start_time.split(" ")
    end_date, end_clock = end_time.split(" ")
    opened = scope.evaluate(
        """
        () => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const rectOf = (el) => el.getBoundingClientRect();
            const textOf = (el) => `${el.value || ''} ${el.placeholder || ''} ${el.innerText || el.textContent || ''}`;
            const inputs = Array.from(document.querySelectorAll('input')).filter((el) => {
                const rect = rectOf(el);
                return isVisible(el) && el.type !== 'checkbox' && el.type !== 'hidden'
                    && rect.width > 40 && rect.height > 18 && rect.top > 80 && rect.top < 430;
            });

            const payStartText = '\\u4ed8\\u6b3e\\u5f00\\u59cb\\u65f6\\u95f4';
            const rangeTextPattern = /\\d{4}-\\d{2}-\\d{2}|\\u5f00\\u59cb\\u65f6\\u95f4|\\u7ed3\\u675f\\u65f6\\u95f4/;
            const payStart = inputs.find((el) => textOf(el).includes(payStartText));
            if (payStart) {
                const payRect = rectOf(payStart);
                const leftInputs = inputs
                    .map((el) => ({ el, rect: rectOf(el), text: textOf(el) }))
                    .filter(({ rect, text }) => {
                        const sameRow = rect.top < payRect.bottom + 14 && rect.bottom > payRect.top - 14;
                        const leftSide = rect.right <= payRect.left + 10;
                        const likelyRange = rect.width >= 150 || rangeTextPattern.test(text);
                        return sameRow && leftSide && likelyRange;
                    })
                    .sort((a, b) => b.rect.right - a.rect.right);
                if (leftInputs.length > 0) {
                    leftInputs[0].el.click();
                    return true;
                }
            }

            const dateInputs = inputs
                .map((el) => ({ el, rect: rectOf(el), text: textOf(el) }))
                .filter(({ rect, text }) => {
                    const inFilterArea = rect.left > 120 && rect.left < 1050;
                    const looksLikeDate = rangeTextPattern.test(text) || rect.width >= 180;
                    return inFilterArea && looksLikeDate;
                })
                .sort((a, b) => (a.rect.top - b.rect.top) || (a.rect.left - b.rect.left));
            if (dateInputs.length > 0) {
                dateInputs[dateInputs.length - 1].el.click();
                return true;
            }
            return false;
        }
        """
    )
    if not opened:
        return False

    scope.page.wait_for_timeout(800)
    filled = scope.evaluate(
        """
        ([startDate, startClock, endDate, endClock]) => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const rectOf = (el) => el.getBoundingClientRect();
            const panels = Array.from(document.querySelectorAll('.el-picker-panel, .el-date-range-picker, .el-popper, [class*="picker"], [class*="popper"]'))
                .filter((el) => isVisible(el))
                .map((el) => ({
                    el,
                    rect: rectOf(el),
                    inputs: Array.from(el.querySelectorAll('input')).filter(isVisible),
                }))
                .filter((item) => item.inputs.length >= 4)
                .sort((a, b) => b.inputs.length - a.inputs.length);
            const panel = panels[0]?.el;
            if (!panel) return false;

            const inputs = Array.from(panel.querySelectorAll('input'))
                .filter(isVisible)
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (ar.top - br.top) || (ar.left - br.left);
                })
                .slice(0, 4);
            if (inputs.length < 4) return false;

            const values = [startDate, startClock, endDate, endClock];
            const setValue = (el, value) => {
                el.removeAttribute('readonly');
                el.removeAttribute('disabled');
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, value);
                else el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.blur();
            };
            inputs.forEach((el, index) => setValue(el, values[index]));

            const confirmText = '\\u786e\\u5b9a';
            const buttons = Array.from(panel.querySelectorAll('button, span, div'))
                .filter(isVisible)
                .filter((el) => (el.innerText || el.textContent || '').trim() === confirmText)
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (br.top - ar.top) || (br.left - ar.left);
                });
            if (buttons[0]) buttons[0].click();
            return true;
        }
        """,
        [start_date, start_clock, end_date, end_clock],
    )
    scope.page.wait_for_timeout(800)
    return bool(filled)


def _fill_date_range_picker_popup_v2(page: Page, start_time: str, end_time: str) -> bool:
    start_date, start_clock = start_time.split(" ")
    end_date, end_clock = end_time.split(" ")
    point = page.evaluate(
        """
        () => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const rectOf = (el) => el.getBoundingClientRect();
            const textOf = (el) => `${el.value || ''} ${el.placeholder || ''} ${el.innerText || el.textContent || ''}`;
            const inputs = Array.from(document.querySelectorAll('input')).filter((el) => {
                const rect = rectOf(el);
                return isVisible(el) && el.type !== 'checkbox' && el.type !== 'hidden'
                    && rect.width > 40 && rect.height > 18 && rect.top > 80 && rect.top < 430;
            });

            const payStartText = '\\u4ed8\\u6b3e\\u5f00\\u59cb\\u65f6\\u95f4';
            const rangeTextPattern = /\\d{4}-\\d{2}-\\d{2}|\\u5f00\\u59cb\\u65f6\\u95f4|\\u7ed3\\u675f\\u65f6\\u95f4/;
            const payStart = inputs.find((el) => textOf(el).includes(payStartText));
            if (payStart) {
                const payRect = rectOf(payStart);
                const leftInputs = inputs
                    .map((el) => ({ el, rect: rectOf(el), text: textOf(el) }))
                    .filter(({ rect, text }) => {
                        const sameRow = rect.top < payRect.bottom + 14 && rect.bottom > payRect.top - 14;
                        const leftSide = rect.right <= payRect.left + 10;
                        const likelyRange = rect.width >= 150 || rangeTextPattern.test(text);
                        return sameRow && leftSide && likelyRange;
                    })
                    .sort((a, b) => b.rect.right - a.rect.right);
                if (leftInputs.length > 0) {
                    const rect = leftInputs[0].rect;
                    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
                }
            }

            const dateInputs = inputs
                .map((el) => ({ el, rect: rectOf(el), text: textOf(el) }))
                .filter(({ rect, text }) => {
                    const inFilterArea = rect.left > 120 && rect.left < 1050;
                    const looksLikeDate = rangeTextPattern.test(text) || rect.width >= 180;
                    return inFilterArea && looksLikeDate;
                })
                .sort((a, b) => (a.rect.top - b.rect.top) || (a.rect.left - b.rect.left));
            if (dateInputs.length > 0) {
                const item = dateInputs[dateInputs.length - 1];
                const rect = item.rect;
                return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
            }
            return null;
        }
        """
    )
    if not point:
        return False

    page.mouse.click(point["x"], point["y"])
    page.wait_for_timeout(800)

    filled = page.evaluate(
        """
        ([startDate, startClock, endDate, endClock]) => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const rectOf = (el) => el.getBoundingClientRect();
            const panels = Array.from(document.querySelectorAll('.el-picker-panel, .el-date-range-picker, .el-popper, [class*="picker"], [class*="popper"]'))
                .filter((el) => isVisible(el))
                .map((el) => ({
                    el,
                    rect: rectOf(el),
                    inputs: Array.from(el.querySelectorAll('input')).filter(isVisible),
                }))
                .filter((item) => item.inputs.length >= 4)
                .sort((a, b) => b.inputs.length - a.inputs.length);
            const panel = panels[0]?.el;
            if (!panel) return false;

            const inputs = Array.from(panel.querySelectorAll('input'))
                .filter(isVisible)
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (ar.top - br.top) || (ar.left - br.left);
                })
                .slice(0, 4);
            if (inputs.length < 4) return false;

            const values = [startDate, startClock, endDate, endClock];
            const setValue = (el, value) => {
                el.removeAttribute('readonly');
                el.removeAttribute('disabled');
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, value);
                else el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.blur();
            };
            inputs.forEach((el, index) => setValue(el, values[index]));

            const confirmText = '\\u786e\\u5b9a';
            const buttons = Array.from(panel.querySelectorAll('button, span, div'))
                .filter(isVisible)
                .filter((el) => (el.innerText || el.textContent || '').trim() === confirmText)
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (br.top - ar.top) || (br.left - ar.left);
                });
            if (buttons[0]) buttons[0].click();
            return true;
        }
        """,
        [start_date, start_clock, end_date, end_clock],
    )
    page.wait_for_timeout(800)
    return bool(filled)


def _fill_date_range_picker_popup(page: Page, start_time: str, end_time: str) -> bool:
    start_date, start_clock = start_time.split(" ")
    end_date, end_clock = end_time.split(" ")
    point = page.evaluate(
        """
        () => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const rectOf = (el) => el.getBoundingClientRect();
            const textOf = (el) => `${el.value || ''} ${el.placeholder || ''} ${el.innerText || el.textContent || ''}`;
            const inputs = Array.from(document.querySelectorAll('input')).filter((el) => {
                const rect = rectOf(el);
                return isVisible(el) && el.type !== 'checkbox' && el.type !== 'hidden'
                    && rect.width > 40 && rect.height > 18 && rect.top > 80 && rect.top < 420;
            });

            const payStart = inputs.find((el) => textOf(el).includes('付款开始时间'));
            if (payStart) {
                const payRect = rectOf(payStart);
                const leftInputs = inputs
                    .map((el) => ({ el, rect: rectOf(el), text: textOf(el) }))
                    .filter(({ rect, text }) => {
                        const sameRow = rect.top < payRect.bottom + 14 && rect.bottom > payRect.top - 14;
                        const leftSide = rect.right <= payRect.left + 10;
                        const likelyRange = rect.width >= 150 || /\\d{4}-\\d{2}-\\d{2}|开始时间|结束时间/.test(text);
                        return sameRow && leftSide && likelyRange;
                    })
                    .sort((a, b) => b.rect.right - a.rect.right);
                if (leftInputs.length > 0) {
                    const rect = leftInputs[0].rect;
                    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
                }
            }

            const dateInputs = inputs
                .map((el) => ({ el, rect: rectOf(el), text: textOf(el) }))
                .filter(({ rect, text }) => {
                    const inFilterArea = rect.left > 120 && rect.left < 1000;
                    const looksLikeDate = /\\d{4}-\\d{2}-\\d{2}|开始时间|结束时间/.test(text) || rect.width >= 180;
                    return inFilterArea && looksLikeDate;
                })
                .sort((a, b) => (a.rect.top - b.rect.top) || (a.rect.left - b.rect.left));
            if (dateInputs.length > 0) {
                const item = dateInputs[dateInputs.length - 1];
                const rect = item.rect;
                return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
            }
            return null;
        }
        """
    )
    if not point:
        return False

    page.mouse.click(point["x"], point["y"])
    page.wait_for_timeout(800)

    filled = page.evaluate(
        """
        ([startDate, startClock, endDate, endClock]) => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const rectOf = (el) => el.getBoundingClientRect();
            const panels = Array.from(document.querySelectorAll('.el-picker-panel, .el-date-range-picker, .el-popper, [class*="picker"], [class*="popper"]'))
                .filter((el) => isVisible(el))
                .map((el) => ({
                    el,
                    rect: rectOf(el),
                    inputs: Array.from(el.querySelectorAll('input')).filter(isVisible),
                }))
                .filter((item) => item.inputs.length >= 4)
                .sort((a, b) => b.inputs.length - a.inputs.length);
            const panel = panels[0]?.el;
            if (!panel) return false;

            const inputs = Array.from(panel.querySelectorAll('input'))
                .filter(isVisible)
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (ar.top - br.top) || (ar.left - br.left);
                })
                .slice(0, 4);
            if (inputs.length < 4) return false;

            const values = [startDate, startClock, endDate, endClock];
            const setValue = (el, value) => {
                el.removeAttribute('readonly');
                el.removeAttribute('disabled');
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, value);
                else el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
                el.blur();
            };
            inputs.forEach((el, index) => setValue(el, values[index]));

            const buttons = Array.from(panel.querySelectorAll('button, span, div'))
                .filter(isVisible)
                .filter((el) => (el.innerText || el.textContent || '').trim() === '确定')
                .sort((a, b) => {
                    const ar = rectOf(a);
                    const br = rectOf(b);
                    return (br.top - ar.top) || (br.left - ar.left);
                });
            if (buttons[0]) buttons[0].click();
            return true;
        }
        """,
        [start_date, start_clock, end_date, end_clock],
    )
    page.wait_for_timeout(800)
    return bool(filled)


def _fill_visible_date_range_by_dom(page: Page, start_time: str, end_time: str) -> bool:
    return bool(
        page.evaluate(
            """
            ([startTime, endTime]) => {
                const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const setValue = (el, value) => {
                    el.removeAttribute('readonly');
                    el.removeAttribute('disabled');
                    el.focus();
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                    if (setter) setter.call(el, value);
                    else el.value = value;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
                    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
                    el.blur();
                };

                const visibleInputs = Array.from(document.querySelectorAll('input'))
                    .filter((el) => isVisible(el) && el.type !== 'checkbox' && el.type !== 'hidden');
                const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s/g, '');
                const rectOf = (el) => el.getBoundingClientRect();

                const labels = Array.from(document.querySelectorAll('label, span, div, td'))
                    .filter((el) => {
                        if (!isVisible(el)) return false;
                        const rect = rectOf(el);
                        const text = textOf(el);
                        return text.includes('发货时间') && rect.width > 0 && rect.height > 0;
                    })
                    .sort((a, b) => {
                        const ar = rectOf(a);
                        const br = rectOf(b);
                        return (ar.width * ar.height) - (br.width * br.height);
                    });

                for (const label of labels) {
                    const labelRect = rectOf(label);
                    const rowInputs = visibleInputs
                        .map((el) => ({ el, rect: rectOf(el) }))
                        .filter(({ rect }) => {
                            const sameRow = rect.top < labelRect.bottom + 28 && rect.bottom > labelRect.top - 28;
                            const rightSide = rect.left > labelRect.left;
                            return sameRow && rightSide && rect.width >= 80 && rect.height >= 20;
                        })
                        .sort((a, b) => a.rect.left - b.rect.left);
                    if (rowInputs.length >= 2) {
                        setValue(rowInputs[0].el, startTime);
                        setValue(rowInputs[1].el, endTime);
                        return true;
                    }
                }

                const dateLikeInputs = visibleInputs
                    .map((el) => ({ el, rect: rectOf(el), value: el.value || '', placeholder: el.getAttribute('placeholder') || '' }))
                    .filter(({ rect, value, placeholder }) => {
                        const text = `${value} ${placeholder}`;
                        const looksDate = /\\d{4}-\\d{2}-\\d{2}|开始时间|结束时间/.test(text);
                        const likelyFilterArea = rect.top > 120 && rect.top < 360 && rect.left < 1000;
                        return rect.width >= 120 && rect.height >= 20 && (looksDate || likelyFilterArea);
                    })
                    .sort((a, b) => (a.rect.top - b.rect.top) || (a.rect.left - b.rect.left));

                for (let i = 0; i < dateLikeInputs.length - 1; i += 1) {
                    const first = dateLikeInputs[i];
                    const second = dateLikeInputs[i + 1];
                    const sameRow = Math.abs(first.rect.top - second.rect.top) < 12;
                    const close = second.rect.left > first.rect.left && second.rect.left - first.rect.left < 360;
                    if (sameRow && close) {
                        setValue(first.el, startTime);
                        setValue(second.el, endTime);
                        return true;
                    }
                }

                return false;
            }
            """,
            [start_time, end_time],
        )
    )


def _set_text_input(locator: Locator, value: str) -> None:
    locator.click()
    locator.fill("")
    locator.fill(value)
    locator.press("Enter")
    locator.press("Tab")


def _start_export_filtered_data(page: Page) -> None:
    _dump_erp_stage_debug(page, "before_export")
    if not _hover_visible_text_by_mouse_anywhere(page, "导出", min_y=250, prefer_right=True, wait_ms=1_000):
        _click_text(page, "导出", exact=True)
    page.wait_for_timeout(2_000)
    _dump_erp_stage_debug(page, "export_menu")
    if not _click_visible_text_by_mouse_anywhere(page, "导出筛选数据"):
        if page.get_by_text("导出筛选数据", exact=True).count() > 0:
            page.get_by_text("导出筛选数据", exact=True).click()
        elif not _click_visible_text_by_mouse_anywhere(page, "导出全部筛选数据"):
            _click_text(page, "导出全部筛选数据", exact=True)
    page.wait_for_timeout(2_000)
    _dump_erp_stage_debug(page, "export_settings")
    if not _click_visible_text_by_mouse_anywhere(page, "确认"):
        if not _click_visible_text_by_mouse_anywhere(page, "确定"):
            _click_button_or_text(page, "确认")
    page.wait_for_timeout(2_000)
    _dump_erp_stage_debug(page, "after_export_confirm")


def _open_export_records(page: Page) -> None:
    _dump_erp_stage_debug(page, "before_export_records")
    if not _click_visible_text_by_mouse_anywhere(page, "查看导出记录"):
        if page.get_by_text("查看导出记录", exact=True).count() > 0:
            page.get_by_text("查看导出记录", exact=True).click()
        else:
            if not _hover_visible_text_by_mouse_anywhere(page, "导出", min_y=250, prefer_right=True, wait_ms=1_000):
                _click_text(page, "导出", exact=True)
            page.wait_for_timeout(2_000)
            if not _click_visible_text_by_mouse_anywhere(page, "查看导出记录"):
                _click_text(page, "查看导出记录", exact=True)

    page.wait_for_timeout(2_000)
    _dump_erp_stage_debug(page, "export_records")


def _download_latest_export(page: Page) -> None:
    last_debug_at = -1
    for attempt in range(36):
        if attempt in {0, 6, 18, 35} and attempt != last_debug_at:
            _dump_erp_stage_debug(page, f"export_records_wait_{attempt:02d}")
            last_debug_at = attempt

        if _click_export_record_download(page):
            return

        if page.get_by_text("刷新", exact=True).count() > 0:
            try:
                page.get_by_text("刷新", exact=True).click()
            except Exception:
                pass
        page.wait_for_timeout(2_000)

    _dump_erp_stage_debug(page, "export_records_download_missing")
    if not _click_visible_text_by_mouse_anywhere(page, "下载"):
        _click_text(page, "下载", exact=True)


def _click_export_record_download(page: Page) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            download_locator = scope.get_by_text("\u4e0b\u8f7d", exact=True)
            count = min(download_locator.count(), 10)
            for index in range(count):
                candidate = download_locator.nth(index)
                if not candidate.is_visible(timeout=1_000):
                    continue

                box = candidate.bounding_box(timeout=1_000)
                if box and box.get("y", 0) < 40:
                    continue

                candidate.click(timeout=5_000, force=True)
                page.wait_for_timeout(1_000)
                print(
                    "ERP clicked export download via frame locator "
                    f"index={index} box={box}"
                )
                return True
        except Exception as exc:
            print(f"ERP frame locator download click failed: {exc}")

        try:
            target = scope.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden'
                            && style.display !== 'none'
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, '').trim();
                    const clickable = (el) => {
                        let current = el;
                        for (let i = 0; current && i < 6; i += 1) {
                            const className = String(current.className || '');
                            if (
                                ['A', 'BUTTON'].includes(current.tagName)
                                || current.getAttribute('role') === 'button'
                                || className.includes('el-button')
                                || className.includes('ant-btn')
                                || className.includes('ivu-btn')
                                || className.includes('btn')
                            ) {
                                return current;
                            }
                            current = current.parentElement;
                        }
                        return el;
                    };
                    const candidates = Array.from(document.querySelectorAll('a, button, span, div'))
                        .filter((el) => isVisible(el) && textOf(el) === '下载')
                        .map((el) => {
                            const clickTarget = clickable(el);
                            const rect = clickTarget.getBoundingClientRect();
                            const row = clickTarget.closest('tr, .ant-table-row, .el-table__row');
                            const rowRect = row ? row.getBoundingClientRect() : null;
                            return {
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                                rowY: rowRect ? rowRect.top : rect.top,
                                right: rect.right,
                                tag: clickTarget.tagName,
                                className: String(clickTarget.className || ''),
                                href: clickTarget.getAttribute('href') || '',
                                download: clickTarget.getAttribute('download') || '',
                            };
                        })
                        .filter((item) => item.y >= 60);
                    candidates.sort((a, b) => {
                        if (Math.abs(a.rowY - b.rowY) > 2) return a.rowY - b.rowY;
                        return b.right - a.right;
                    });
                    return candidates[0] || null;
                }
                """
            )
        except Exception:
            target = None

        if not target:
            continue

        try:
            dom_clicked = bool(
                scope.evaluate(
                    """
                    () => {
                        const isVisible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.visibility !== 'hidden'
                                && style.display !== 'none'
                                && rect.width > 0
                                && rect.height > 0;
                        };
                        const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, '').trim();
                        const clickable = (el) => {
                            let current = el;
                            for (let i = 0; current && i < 6; i += 1) {
                                const className = String(current.className || '');
                                if (
                                    ['A', 'BUTTON'].includes(current.tagName)
                                    || current.getAttribute('role') === 'button'
                                    || className.includes('el-button')
                                    || className.includes('ant-btn')
                                    || className.includes('ivu-btn')
                                    || className.includes('btn')
                                ) {
                                    return current;
                                }
                                current = current.parentElement;
                            }
                            return el;
                        };
                        const candidates = Array.from(document.querySelectorAll('a, button, span, div'))
                            .filter((el) => isVisible(el) && textOf(el) === '\\u4e0b\\u8f7d')
                            .map((el) => {
                                const clickTarget = clickable(el);
                                const rect = clickTarget.getBoundingClientRect();
                                const row = clickTarget.closest('tr, .ant-table-row, .el-table__row');
                                const rowRect = row ? row.getBoundingClientRect() : null;
                                return {
                                    clickTarget,
                                    rowY: rowRect ? rowRect.top : rect.top,
                                    right: rect.right,
                                    y: rect.top,
                                };
                            })
                            .filter((item) => item.y >= 60);
                        candidates.sort((a, b) => {
                            if (Math.abs(a.rowY - b.rowY) > 2) return a.rowY - b.rowY;
                            return b.right - a.right;
                        });
                        if (!candidates[0]) return false;
                        candidates[0].clickTarget.click();
                        return true;
                    }
                    """
                )
            )
        except Exception as exc:
            dom_clicked = False
            print(f"ERP DOM download click failed: {exc}")

        page.wait_for_timeout(500)
        page.mouse.click(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2)
        page.wait_for_timeout(1_000)
        print(
            f"ERP clicked export download at x={target['x']:.1f} y={target['y']:.1f} "
            f"w={target['width']:.1f} h={target['height']:.1f} "
            f"dom_clicked={dom_clicked} tag={target.get('tag', '')} "
            f"class={target.get('className', '')} href={target.get('href', '')}"
        )
        return True

    return False


def _snapshot_download_files(download_dir: Path) -> set[Path]:
    download_dir.mkdir(parents=True, exist_ok=True)
    return {path.resolve() for path in download_dir.glob("*") if path.is_file()}


def _wait_for_new_download_file(download_dir: Path, before_files: set[Path], page: Page) -> Path:
    suffixes = {".xlsx", ".xls", ".csv"}
    for attempt in range(60):
        candidates = [
            path
            for path in download_dir.glob("*")
            if path.is_file()
            and path.resolve() not in before_files
            and path.suffix.lower() in suffixes
            and not path.name.endswith(".crdownload")
        ]
        if candidates:
            candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            return candidates[0]

        if attempt in {0, 10, 30, 59}:
            _dump_erp_stage_debug(page, f"download_dir_wait_{attempt:02d}")
        page.wait_for_timeout(3_000)

    existing = "\n".join(str(path) for path in sorted(download_dir.glob("*"))[-20:])
    raise RuntimeError(f"ERP download did not create a file in {download_dir}. Existing files:\n{existing}")


def _dump_erp_date_debug(page: Page) -> None:
    debug_dir = Path("logs")
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "erp_date_debug.html").write_text(page.content(), encoding="utf-8")
    inputs = page.locator("input").evaluate_all(
        """els => els.map((e, i) => ({
            index: i,
            placeholder: e.getAttribute('placeholder'),
            value: e.value,
            ariaLabel: e.getAttribute('aria-label'),
            title: e.getAttribute('title'),
            text: e.closest('.ant-form-item, .el-form-item, td, div')?.innerText,
            outerHTML: e.outerHTML.slice(0, 500)
        }))"""
    )
    (debug_dir / "erp_date_debug_inputs.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    frame_debug = []
    for index, frame in enumerate(page.frames):
        try:
            frame_inputs = frame.locator("input").evaluate_all(
                """els => els.map((e, i) => ({
                    index: i,
                    type: e.type,
                    placeholder: e.getAttribute('placeholder'),
                    value: e.type === 'password' ? '***' : e.value,
                    visible: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
                    rect: (() => {
                        const r = e.getBoundingClientRect();
                        return { x: r.x, y: r.y, width: r.width, height: r.height };
                    })(),
                    outerHTML: e.outerHTML.slice(0, 300)
                }))"""
            )
            body_text = frame.locator("body").inner_text(timeout=2_000)
            frame_debug.append(
                {
                    "index": index,
                    "url": frame.url,
                    "text": body_text[:1000],
                    "input_count": len(frame_inputs),
                    "inputs": frame_inputs[:80],
                }
            )
        except Exception as exc:
            frame_debug.append({"index": index, "url": getattr(frame, "url", ""), "error": str(exc)})
    (debug_dir / "erp_date_debug_frames.json").write_text(
        json.dumps(frame_debug, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("--- erp date frame debug ---")
    print(json.dumps(frame_debug, ensure_ascii=False, indent=2)[:6000])


def _dump_erp_login_debug(page: Page) -> None:
    debug_dir = Path("logs")
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "erp_login_debug.html").write_text(page.content(), encoding="utf-8")
    (debug_dir / "erp_login_debug_text.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    inputs = page.locator("input").evaluate_all(
        """els => els.map((e, i) => ({
            index: i,
            type: e.type,
            placeholder: e.getAttribute('placeholder'),
            value: e.type === 'password' ? '***' : e.value,
            visible: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
            outerHTML: e.outerHTML.slice(0, 500)
        }))"""
    )
    (debug_dir / "erp_login_debug_inputs.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _dump_erp_navigation_debug(page: Page) -> None:
    debug_dir = Path("logs")
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "erp_navigation_debug.html").write_text(page.content(), encoding="utf-8")
    (debug_dir / "erp_navigation_debug_text.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    page.screenshot(path=str(debug_dir / "erp_navigation_debug.png"), full_page=True)


def _dump_erp_stage_debug(page: Page, name: str) -> None:
    debug_dir = Path("logs")
    debug_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text_path = debug_dir / f"erp_{safe_name}_debug_text.txt"
    image_path = debug_dir / f"erp_{safe_name}_debug.png"
    stamped_text_path = debug_dir / f"erp_{safe_name}_debug_{timestamp}.txt"
    stamped_image_path = debug_dir / f"erp_{safe_name}_debug_{timestamp}.png"
    text = page.locator("body").inner_text()
    text_path.write_text(text, encoding="utf-8")
    stamped_text_path.write_text(text, encoding="utf-8")
    page.screenshot(path=str(image_path), full_page=True)
    page.screenshot(path=str(stamped_image_path), full_page=True)
    print(f"ERP debug snapshot saved: {image_path} and {stamped_image_path}")


def _click_button_or_text_anywhere(page: Page, text: str) -> None:
    if text == "\u7b5b\u9009" and _click_filter_button_by_position(page):
        return

    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            button = scope.get_by_role("button", name=text)
            if button.count() > 0:
                button.first().click()
                return
            locator = scope.get_by_text(text, exact=False)
            if locator.count() > 0:
                locator.first().click()
                return
        except Exception:
            continue
    _click_button_or_text(page, text)


def _click_visible_text_by_dom_anywhere(
    page: Page,
    text: str,
    *,
    min_y: int = 0,
    prefer_right: bool = False,
) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            clicked = scope.evaluate(
                """
                ({ targetText, minY, preferRight }) => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden'
                            && style.display !== 'none'
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                    const candidates = Array.from(document.querySelectorAll('body *'))
                        .filter((el) => isVisible(el) && textOf(el) === targetText)
                        .map((el) => {
                            const rect = el.getBoundingClientRect();
                            return { el, x: rect.left, y: rect.top, width: rect.width, height: rect.height };
                        })
                        .filter((item) => item.y >= minY);
                    candidates.sort((a, b) => {
                        if (preferRight && Math.abs(b.x - a.x) > 2) return b.x - a.x;
                        const areaDiff = (a.width * a.height) - (b.width * b.height);
                        if (Math.abs(areaDiff) > 2) return areaDiff;
                        if (Math.abs(a.y - b.y) > 2) return a.y - b.y;
                        return a.x - b.x;
                    });
                    const target = candidates[0];
                    if (!target) return null;
                    target.el.click();
                    return {
                        text: targetText,
                        x: target.x,
                        y: target.y,
                        width: target.width,
                        height: target.height,
                        tag: target.el.tagName,
                        className: target.el.className || '',
                    };
                }
                """,
                {"targetText": text, "minY": min_y, "preferRight": prefer_right},
            )
            if clicked:
                print(f"ERP clicked visible text via DOM: {clicked}")
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False


def _click_visible_text_by_mouse_anywhere(
    page: Page,
    text: str,
    *,
    min_y: int = 0,
    prefer_right: bool = False,
) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            target = scope.evaluate(
                """
                ({ targetText, minY, preferRight }) => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden'
                            && style.display !== 'none'
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                    const candidates = Array.from(document.querySelectorAll('body *'))
                        .filter((el) => isVisible(el) && textOf(el) === targetText)
                        .map((el) => {
                            const rect = el.getBoundingClientRect();
                            return {
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                                tag: el.tagName,
                                className: el.className || '',
                            };
                        })
                        .filter((item) => item.y >= minY);
                    candidates.sort((a, b) => {
                        if (preferRight && Math.abs(b.x - a.x) > 2) return b.x - a.x;
                        const areaDiff = (a.width * a.height) - (b.width * b.height);
                        if (Math.abs(areaDiff) > 2) return areaDiff;
                        if (Math.abs(a.y - b.y) > 2) return a.y - b.y;
                        return a.x - b.x;
                    });
                    return candidates[0] || null;
                }
                """,
                {"targetText": text, "minY": min_y, "preferRight": prefer_right},
            )
            if not target:
                continue
            offset_x = 0
            offset_y = 0
            if scope != page.main_frame:
                frame_box = scope.frame_element().bounding_box()
                if frame_box:
                    offset_x = frame_box["x"]
                    offset_y = frame_box["y"]
            x = target["x"] + offset_x + target["width"] / 2
            y = target["y"] + offset_y + target["height"] / 2
            page.mouse.click(x, y)
            print(f"ERP clicked visible text via mouse: {text} at x={x}, y={y}, target={target}")
            page.wait_for_timeout(500)
            return True
        except Exception:
            continue
    return _click_visible_text_by_dom_anywhere(page, text, min_y=min_y, prefer_right=prefer_right)


def _hover_visible_text_by_mouse_anywhere(
    page: Page,
    text: str,
    *,
    min_y: int = 0,
    prefer_right: bool = False,
    wait_ms: int = 1_000,
) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            target = _find_visible_text_target(scope, text, min_y=min_y, prefer_right=prefer_right)
            if not target:
                continue
            offset_x = 0
            offset_y = 0
            if scope != page.main_frame:
                frame_box = scope.frame_element().bounding_box()
                if frame_box:
                    offset_x = frame_box["x"]
                    offset_y = frame_box["y"]
            x = target["x"] + offset_x + target["width"] / 2
            y = target["y"] + offset_y + target["height"] / 2
            page.mouse.move(x, y)
            print(f"ERP hovered visible text via mouse: {text} at x={x}, y={y}, target={target}")
            page.wait_for_timeout(wait_ms)
            return True
        except Exception:
            continue
    return False


def _find_visible_text_target(scope, text: str, *, min_y: int = 0, prefer_right: bool = False):
    return scope.evaluate(
        """
        ({ targetText, minY, preferRight }) => {
            const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden'
                    && style.display !== 'none'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            const candidates = Array.from(document.querySelectorAll('body *'))
                .filter((el) => isVisible(el) && textOf(el) === targetText)
                .map((el) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        x: rect.left,
                        y: rect.top,
                        width: rect.width,
                        height: rect.height,
                        tag: el.tagName,
                        className: el.className || '',
                    };
                })
                .filter((item) => item.y >= minY);
            candidates.sort((a, b) => {
                if (preferRight && Math.abs(b.x - a.x) > 2) return b.x - a.x;
                const areaDiff = (a.width * a.height) - (b.width * b.height);
                if (Math.abs(areaDiff) > 2) return areaDiff;
                if (Math.abs(a.y - b.y) > 2) return a.y - b.y;
                return a.x - b.x;
            });
            return candidates[0] || null;
        }
        """,
        {"targetText": text, "minY": min_y, "preferRight": prefer_right},
    )


def _click_filter_button_by_position(page: Page) -> bool:
    scopes = [page.main_frame] + [frame for frame in page.frames if frame != page.main_frame]
    for scope in scopes:
        try:
            target = scope.evaluate(
                """
                () => {
                    const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s/g, '');
                    const buttons = Array.from(document.querySelectorAll('button, a, div, span'))
                        .filter((el) => isVisible(el) && textOf(el) === '筛选')
                        .map((el) => {
                            const target = el.closest('button, a, [role="button"], .el-button, .ant-btn, .ivu-btn') || el;
                            const rect = target.getBoundingClientRect();
                            const style = window.getComputedStyle(target);
                            const className = String(target.className || '');
                            const blueScore = (
                                className.includes('primary')
                                || style.backgroundColor.includes('64, 158, 255')
                                || style.backgroundColor.includes('24, 144, 255')
                                || style.backgroundColor.includes('45, 140, 240')
                            ) ? 0 : 1;
                            return {
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                                blueScore,
                            };
                        })
                        .filter((item) => item.width >= 35 && item.width <= 120 && item.height >= 24 && item.height <= 60);
                    buttons.sort((a, b) => a.blueScore - b.blueScore || b.y - a.y || a.x - b.x);
                    if (buttons[0]) return { ...buttons[0], mode: 'button' };

                    const editor = Array.from(document.querySelectorAll('.el-date-editor.el-range-editor, .el-range-editor, .el-date-editor'))
                        .find((el) => isVisible(el) && el.getBoundingClientRect().width > 120);
                    if (!editor) return null;
                    const r = editor.getBoundingClientRect();
                    return { x: r.left + 670, y: r.top + 130, width: 1, height: 1, mode: 'offset' };
                }
                """
            )
            if not target:
                continue
            offset_x = 0
            offset_y = 0
            if scope != page.main_frame:
                frame_box = scope.frame_element().bounding_box()
                if frame_box:
                    offset_x = frame_box["x"]
                    offset_y = frame_box["y"]
            page.mouse.click(target["x"] + offset_x + target["width"] / 2, target["y"] + offset_y + target["height"] / 2)
            page.wait_for_timeout(500)
            print(f"ERP clicked filter button via {target.get('mode', 'unknown')}")
            return True
        except Exception:
            continue
    return False


def _click_button_or_text(page: Page, text: str) -> None:
    button = page.get_by_role("button", name=text)
    if button.count() > 0:
        button.first().click()
        return
    _click_text(page, text)


def _click_text(page: Page, text: str, *, exact: bool = False) -> None:
    locator = page.get_by_text(text, exact=exact)
    if locator.count() == 0:
        raise RuntimeError(f"Cannot find text on ERP page: {text}")
    locator.first().click()
