from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import Settings
from .models import AlertItem, AuditSummary


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def upload_erp_file_to_audit(settings: Settings, file_path: Path) -> None:
    upload_erp_file_to_audit_for_date(settings, file_path, _target_order_date())


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def upload_erp_file_to_audit_for_date(
    settings: Settings, file_path: Path, target_date: date
) -> None:
    print(f"Audit upload start: date={target_date:%Y-%m-%d} file={file_path}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(settings.audit_url, wait_until="domcontentloaded")
        print(f"Audit page loaded: url={page.url}")
        _dump_audit_debug(page, "loaded")

        _login_if_needed(page, settings)
        _open_daily_profit_radar(page)
        _choose_calendar_day(page, target_date)
        print(f"Audit selected date: {target_date:%Y-%m-%d}")
        _upload_file(page, file_path)
        print(f"Audit upload completed: date={target_date:%Y-%m-%d} file={file_path}")

        context.close()
        browser.close()


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def read_audit_summary(settings: Settings) -> AuditSummary:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(settings.audit_url, wait_until="domcontentloaded")

        _login_if_needed(page, settings)
        _open_daily_profit_radar(page)
        _choose_calendar_day(page, _target_order_date())
        page.reload(wait_until="networkidle")
        _choose_calendar_day(page, _target_order_date())
        page.wait_for_timeout(2_000)

        summary = _extract_summary(page)
        context.close()
        browser.close()
        return summary


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def read_alerts(settings: Settings) -> list[AlertItem]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(settings.audit_url, wait_until="domcontentloaded")

        _login_if_needed(page, settings)
        _open_daily_profit_radar(page)
        _choose_calendar_day(page, _target_order_date())
        alerts = _extract_alerts(page)

        context.close()
        browser.close()
        return alerts


def _target_order_date() -> date:
    return date.today() - timedelta(days=1)


def _login_if_needed(page: Page, settings: Settings) -> None:
    password_inputs = page.locator("input[type='password']")
    password_count = password_inputs.count()
    print(f"Audit login check: url={page.url} password_inputs={password_count}")
    if password_count == 0:
        print("Audit already logged in")
        return

    _dump_audit_debug(page, "before_login")
    filled = page.evaluate(
        """
        ([username, password]) => {
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const setValue = (el, value) => {
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                setter.call(el, value);
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            };
            const inputs = Array.from(document.querySelectorAll('input')).filter(isVisible);
            const passwordInput = inputs.find((el) => (el.type || '').toLowerCase() === 'password');
            const usernameInput = inputs.find((el) => el !== passwordInput && (el.type || '').toLowerCase() !== 'hidden');
            if (!usernameInput || !passwordInput) {
                return { ok: false, inputCount: inputs.length };
            }
            setValue(usernameInput, username);
            setValue(passwordInput, password);
            return {
                ok: true,
                inputCount: inputs.length,
                usernameType: usernameInput.type || '',
                passwordType: passwordInput.type || '',
            };
        }
        """,
        [settings.audit_username, settings.audit_password],
    )
    print(f"Audit login fields filled: {filled}")

    text_inputs = page.locator("input[type='text']")
    if text_inputs.count() > 0:
        text_inputs.first.fill(settings.audit_username)
    password_inputs.first.fill(settings.audit_password)

    clicked = page.evaluate(
        r"""
        () => {
            const textOf = (el) => (el.innerText || el.textContent || '').replace(/\s/g, '');
            const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const candidates = Array.from(document.querySelectorAll('button, [role=button], a, div, span'))
                .filter((el) => isVisible(el) && ['登录', '登陆', '进入指挥舱'].includes(textOf(el)));
            const target = candidates.find((el) => el.closest('button, [role=button], a')) || candidates[0];
            if (!target) return false;
            const clickable = target.closest('button, [role=button], a') || target;
            clickable.click();
            return true;
        }
        """
    )
    page.wait_for_timeout(8_000)
    print(f"Audit login submitted: clicked={clicked} url={page.url}")
    _dump_audit_debug(page, "after_login")


def _open_daily_profit_radar(page: Page) -> None:
    if "/daily" in page.url:
        print("Audit daily page already open")
        _dump_audit_debug(page, "daily_page")
        return

    page.goto("https://audit.meelolo.com/daily", wait_until="domcontentloaded")
    page.wait_for_timeout(2_000)
    if "/daily" in page.url:
        print("Audit daily page opened by direct url")
        _dump_audit_debug(page, "daily_page")
        return

    _click_text(page, "\u6bcf\u65e5\u5229\u6da6\u4e0e\u9632\u9519\u96f7\u8fbe")
    page.wait_for_timeout(2_000)
    print("Audit daily page opened")
    _dump_audit_debug(page, "daily_page")


def _choose_calendar_day(page: Page, target_date: date) -> None:
    day_text = str(target_date.day)
    selected = page.evaluate(
        """
        (dayText) => {
            const candidates = Array.from(document.querySelectorAll('button, [role=button], div, span'))
                .filter((el) => {
                    const text = (el.innerText || el.textContent || '').trim();
                    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    return visible && text === dayText;
                });
            const target = candidates.find((el) => {
                const rect = el.getBoundingClientRect();
                return rect.width >= 20 && rect.width <= 90 && rect.height >= 20 && rect.height <= 70;
            }) || candidates[0];
            if (!target) return false;
            target.click();
            return true;
        }
        """,
        day_text,
    )
    if not selected:
        _click_text(page, day_text, exact=True)

    page.wait_for_timeout(1_000)
    print(f"Audit calendar day clicked: {day_text}")


def _upload_file(page: Page, file_path: Path) -> None:
    _dump_audit_debug(page, "before_file_select")
    page.set_input_files("input[type=file]", str(file_path))
    print(f"Audit file selected: {file_path}")
    _click_button_or_text(page, "\u63d0\u4ea4\u5e76\u6e05\u6d17\u9884\u4f30")
    page.wait_for_timeout(10_000)
    print("Audit submit button clicked")
    _dump_audit_debug(page, "after_submit")


def _extract_summary(page: Page) -> AuditSummary:
    text = _visible_text(page)
    report_date = _extract_report_date(text)
    total_orders = _extract_total_orders(text)
    suspected_loss_links = _extract_suspected_loss_count(text)
    daily_metrics = _extract_daily_table_metrics(text)

    return AuditSummary(
        report_date=report_date,
        total_orders=total_orders,
        successful_orders=total_orders,
        failed_orders=0,
        suspected_loss_links=suspected_loss_links,
        detail_url=page.url,
        current_profit=_extract_money_after_label(text, "\u5f53\u65e5\u9884\u4f30\u5229\u6da6"),
        daily_revenue=daily_metrics.get("revenue", ""),
        daily_goods_cost=daily_metrics.get("goods_cost", ""),
        daily_platform_fee=daily_metrics.get("platform_fee", ""),
        daily_shipping_fee=daily_metrics.get("shipping_fee", ""),
        daily_ad_spend=daily_metrics.get("ad_spend", ""),
        monthly_profit=_extract_money_after_label(text, "\u672c\u6708\u52a8\u6001\u7d2f\u8ba1"),
        revenue=_extract_money_after_label(text, "\u9884\u4f30\u7d2f\u8ba1\u5e94\u6536"),
        goods_cost=_extract_money_after_label(text, "\u9884\u4f30\u7d2f\u8ba1\u8d27\u672c"),
        platform_fee=_extract_money_after_label(text, "\u9884\u4f30\u7d2f\u8ba1\u5e73\u53f0\u8d39"),
        shipping_fee=_extract_money_after_label(text, "\u9884\u4f30\u7d2f\u8ba1\u8fd0\u8d39"),
        ad_spend=_extract_money_after_label(text, "\u9884\u4f30\u7d2f\u8ba1\u6295\u6d41\u8d39"),
    )


def _extract_alerts(page: Page) -> list[AlertItem]:
    text = _visible_text(page)
    if _extract_suspected_loss_count(text) == 0:
        return []

    return [
        AlertItem(
            alert_type="suspected_loss",
            title="\u7591\u4f3c\u4e8f\u635f\u8ba2\u5355\u63d0\u9192",
            detail="\u8bf7\u6253\u5f00audit\u6bcf\u65e5\u5229\u6da6\u4e0e\u9632\u9519\u96f7\u8fbe\uff0c\u67e5\u770bT+1\u5f02\u5e38\u9632\u635f/\u7f8a\u6bdb\u515a\u96f7\u8fbe\u533a\u5757\u3002",
            detail_url=page.url,
            dedupe_key=f"suspected_loss:{_extract_report_date(text)}",
        )
    ]


def _visible_text(page: Page) -> str:
    return page.evaluate(
        """
        () => String((document.body && (document.body.innerText || document.body.textContent)) || '')
        """
    )


def _extract_money_after_label(text: str, label: str) -> str:
    pattern = re.escape(label) + r"[\s\S]{0,80}?([+-]?\s*(?:\uffe5|\u00a5)?\s*[\d,]+(?:\.\d+)?)"
    match = re.search(pattern, text)
    if not match:
        return ""
    return _normalize_money(match.group(1))


def _normalize_money(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    compact = compact.replace("\u00a5", "\uffe5")
    if compact and not compact.startswith(("\uffe5", "-\uffe5", "+\uffe5")):
        if compact.startswith("-"):
            compact = "-\uffe5" + compact[1:]
        elif compact.startswith("+"):
            compact = "+\uffe5" + compact[1:]
        else:
            compact = "\uffe5" + compact
    return compact


def _extract_report_date(text: str) -> str:
    match = re.search(r"(\d{4})\u5e74(\d{2})\u6708(\d{2})\u65e5\s+\u9884\u4f30\u5229\u6da6\u660e\u7ec6\u8868", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return f"{_target_order_date():%Y-%m-%d}"


def _extract_daily_table_metrics(text: str) -> dict[str, str]:
    table_block = _between(text, "\u5e97\u94fa\u540d\u79f0\t\u53d1\u8d27\u5355\u91cf", "T+1")
    rows = _daily_table_rows(table_block)
    totals = {
        "revenue": 0.0,
        "goods_cost": 0.0,
        "platform_fee": 0.0,
        "shipping_fee": 0.0,
        "ad_spend": 0.0,
    }

    for row in rows:
        amounts = _money_values(row)
        if len(amounts) < 6:
            continue
        totals["revenue"] += amounts[0]
        totals["goods_cost"] += abs(amounts[1])
        totals["platform_fee"] += abs(amounts[2])
        totals["shipping_fee"] += abs(amounts[3])
        totals["ad_spend"] += abs(amounts[-2])

    return {key: _format_money(value) for key, value in totals.items() if value}


def _daily_table_rows(table_block: str) -> list[str]:
    rows: list[list[str]] = []
    current: list[str] = []
    for line in table_block.splitlines():
        if not line.strip():
            continue
        if re.search(r"^[^\t\n]+\t\d+\u5305\u88f9\b", line):
            if current:
                rows.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        rows.append(current)
    return ["\n".join(row) for row in rows]


def _money_values(text: str) -> list[float]:
    return [_money_to_float(value) for value in re.findall(r"[+-]?\s*(?:\uffe5|\u00a5)\s*[\d,]+(?:\.\d+)?", text)]


def _money_to_float(value: str) -> float:
    compact = value.replace("\u00a5", "\uffe5")
    compact = re.sub(r"\s+", "", compact).replace("\uffe5", "").replace(",", "")
    try:
        return float(compact)
    except ValueError:
        return 0.0


def _format_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}\uffe5{abs(value):,.2f}"


def _extract_total_orders(text: str) -> int:
    table_block = _between(text, "\u5e97\u94fa\u540d\u79f0\t\u53d1\u8d27\u5355\u91cf", "T+1")
    package_counts = [
        int(value)
        for value in re.findall(r"(?m)^[^\t\n]+\t(\d+)\u5305\u88f9\b", table_block)
    ]
    if package_counts:
        return sum(package_counts)

    shipping_block = _between(
        text,
        "\u9884\u4f30\u7d2f\u8ba1\u8fd0\u8d39",
        "\u9884\u4f30\u7d2f\u8ba1\u6295\u6d41\u8d39",
    )
    order_counts = [int(value) for value in re.findall(r"(\d+)\u5355", shipping_block)]
    if order_counts:
        return sum(order_counts)

    return sum(int(value) for value in re.findall(r"\t(\d+)\n", table_block))


def _extract_suspected_loss_count(text: str) -> int:
    if "\u672a\u53d1\u73b0\u5f02\u5e38\u4e8f\u635f" in text:
        return 0
    block = _between(text, "\u98ce\u9669\u8ba2\u5355\u53f7", "")
    if not block:
        return 0
    return len(re.findall(r"\b\d{12,}\b", block))


def _between(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    start_index += len(start)
    if not end:
        return text[start_index:]
    end_index = text.find(end, start_index)
    if end_index < 0:
        return text[start_index:]
    return text[start_index:end_index]


def _click_button_or_text(page: Page, text: str) -> None:
    button = page.get_by_role("button", name=text)
    if button.count() > 0:
        button.first.click()
        return
    _click_text(page, text)


def _click_text(page: Page, text: str, *, exact: bool = False) -> None:
    locator = page.get_by_text(text, exact=exact)
    if locator.count() == 0:
        raise RuntimeError(f"Cannot find text on audit page: {text}")
    locator.first.click()


def _dump_audit_debug(page: Page, stage: str) -> None:
    try:
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = logs_dir / f"audit_{stage}_debug.png"
        text_path = logs_dir / f"audit_{stage}_text.txt"
        page.screenshot(path=str(screenshot_path), full_page=True)
        visible_text = page.evaluate(
            """
            () => (document.body && (document.body.innerText || document.body.textContent) || '').slice(0, 4000)
            """
        )
        text_path.write_text(visible_text, encoding="utf-8", errors="ignore")
        print(f"Audit debug saved: {screenshot_path} {text_path}")
    except Exception as exc:
        print(f"Audit debug save failed: stage={stage} error={exc}")
