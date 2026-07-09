from __future__ import annotations

import argparse
from datetime import date, timedelta

from .alert_state import AlertState
from .audit_automation import (
    read_alerts,
    read_audit_summary,
    upload_erp_file_to_audit,
    upload_erp_file_to_audit_for_date,
)
from .config import load_settings
from .cost_reconcile import read_cost_reconcile
from .erp_automation import (
    download_completed_orders_for_date,
    download_yesterday_completed_orders,
)
from .excel_converter import prepare_audit_upload_file
from .feishu import FeishuClient
from .messages import (
    render_alert,
    render_cost_reconcile,
    render_daily_report,
    render_upload_failure,
    render_upload_success,
)


def run_download_upload() -> None:
    settings = load_settings()
    report_date = date.today() - timedelta(days=1)
    try:
        result = download_yesterday_completed_orders(settings)
        upload_file = prepare_audit_upload_file(result.file_path, result.order_date)
        upload_erp_file_to_audit_for_date(settings, upload_file, date.fromisoformat(result.order_date))
    except Exception as exc:
        _send_upload_failure(settings, f"{report_date:%Y-%m-%d}", exc)
        raise

    _send_upload_success(settings, result.order_date, upload_file.name)


def run_download_upload_range(start_date: date, end_date: date) -> None:
    settings = load_settings()
    current = start_date
    while current <= end_date:
        try:
            result = download_completed_orders_for_date(settings, current)
            upload_file = prepare_audit_upload_file(result.file_path, result.order_date)
            upload_erp_file_to_audit_for_date(settings, upload_file, current)
        except Exception as exc:
            _send_upload_failure(settings, f"{current:%Y-%m-%d}", exc)
            raise

        _send_upload_success(settings, result.order_date, upload_file.name)
        current += timedelta(days=1)


def run_report() -> None:
    settings = load_settings()
    summary = read_audit_summary(settings)
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    client.send_text_to_chat(settings.feishu_chat_id, render_daily_report(summary))


def run_alerts() -> None:
    settings = load_settings()
    alerts = read_alerts(settings)
    if not alerts:
        return

    state = AlertState(settings.download_dir / ".alert_state.json")
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    for alert in alerts:
        if state.is_new(alert.dedupe_key):
            client.send_text_to_chat(settings.feishu_chat_id, render_alert(alert))


def run_cost_reconcile() -> None:
    settings = load_settings()
    summary = read_cost_reconcile(settings)
    app_id = settings.cost_feishu_app_id or settings.feishu_app_id
    app_secret = settings.cost_feishu_app_secret or settings.feishu_app_secret
    chat_id = settings.cost_feishu_chat_id or settings.feishu_chat_id
    client = FeishuClient(app_id, app_secret)
    client.send_text_to_chat(chat_id, render_cost_reconcile(summary))


def _send_upload_success(settings, report_date: str, file_name: str) -> None:
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    client.send_text_to_chat(
        settings.feishu_chat_id,
        render_upload_success(report_date, file_name),
    )


def _send_upload_failure(settings, report_date: str, exc: Exception) -> None:
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    client.send_text_to_chat(
        settings.feishu_chat_id,
        render_upload_failure(report_date, str(exc)),
    )


def run_all() -> None:
    run_download_upload()
    run_report()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["run-all", "run-download-upload", "report", "alerts", "cost-reconcile"],
    )
    parser.add_argument("--start-date", help="Backfill start date, format YYYY-MM-DD")
    parser.add_argument("--end-date", help="Backfill end date, format YYYY-MM-DD")
    args = parser.parse_args()

    if args.command == "run-all":
        run_all()
    elif args.command == "run-download-upload":
        if args.start_date or args.end_date:
            if not args.start_date or not args.end_date:
                raise RuntimeError("--start-date and --end-date must be provided together")
            run_download_upload_range(
                date.fromisoformat(args.start_date),
                date.fromisoformat(args.end_date),
            )
        else:
            run_download_upload()
    elif args.command == "report":
        run_report()
    elif args.command == "alerts":
        run_alerts()
    elif args.command == "cost-reconcile":
        run_cost_reconcile()


if __name__ == "__main__":
    main()
