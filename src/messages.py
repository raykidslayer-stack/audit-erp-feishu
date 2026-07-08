from __future__ import annotations

from .models import AlertItem, AuditSummary


def render_upload_success(report_date: str, file_name: str) -> str:
    return "\n".join(
        [
            f"ERP\u8ba2\u5355\u5df2\u63d0\u4ea4\u5230audit - {report_date}",
            "",
            "\u72b6\u6001\uff1a\u5df2\u5b8c\u6210\u4e0b\u8f7d\u3001\u8f6c\u6362\u5e76\u63d0\u4ea4\u6e05\u6d17",
            f"\u6587\u4ef6\uff1a{file_name}",
            "",
            "\u8bf4\u660e\uff1aaudit\u9875\u9762\u53ef\u80fd\u6709\u77ed\u6682\u5237\u65b0\u5ef6\u8fdf\uff0c\u65e5\u5386\u53d8\u7eff\u540e\u5373\u4ee3\u8868\u6e05\u6d17\u5b8c\u6210\u3002",
        ]
    )


def render_upload_failure(report_date: str, error: str) -> str:
    return "\n".join(
        [
            f"ERP\u8ba2\u5355\u4e0a\u4f20\u7591\u4f3c\u5931\u8d25 - {report_date}",
            "",
            "\u72b6\u6001\uff1a\u81ea\u52a8\u5316\u6d41\u7a0b\u6267\u884c\u5931\u8d25",
            f"\u9519\u8bef\uff1a{error}",
            "",
            "\u8bf7\u68c0\u67e5ERP\u4e0b\u8f7d\u3001audit\u4e0a\u4f20\u9875\u9762\u6216\u670d\u52a1\u5668\u65e5\u5fd7\u3002",
        ]
    )


def render_daily_report(summary: AuditSummary) -> str:
    return "\n".join(
        [
            f"audit\u6bcf\u65e5\u5229\u6da6\u65e5\u62a5 - {summary.report_date}",
            "",
            "\u6838\u5fc3\u6307\u6807\uff1a",
            f"\u53d1\u8d27\u5355\u91cf\uff1a{summary.total_orders}",
            f"\u5f53\u65e5\u9884\u4f30\u5229\u6da6\uff1a{summary.current_profit or '-'}",
            f"\u672c\u6708\u52a8\u6001\u7d2f\u8ba1\uff1a{summary.monthly_profit or '-'}",
            "",
            "\u6536\u652f\u62c6\u89e3\uff1a",
            f"\u9884\u4f30\u5e94\u6536\uff1a{summary.revenue or '-'}",
            f"\u9884\u4f30\u8d27\u672c\uff1a{summary.goods_cost or '-'}",
            f"\u9884\u4f30\u5e73\u53f0\u8d39\uff1a{summary.platform_fee or '-'}",
            f"\u9884\u4f30\u8fd0\u8d39\uff1a{summary.shipping_fee or '-'}",
            f"\u9884\u4f30\u6295\u6d41\u8d39\uff1a{summary.ad_spend or '-'}",
            "",
            "\u5f02\u5e38\u63d0\u9192\uff1a",
            f"\u7591\u4f3c\u4e8f\u635f\u8ba2\u5355\uff1a{summary.suspected_loss_links}",
            "",
            f"\u67e5\u770b\u8be6\u60c5\uff1a{summary.detail_url}",
        ]
    )


def render_alert(alert: AlertItem) -> str:
    return "\n".join(
        [
            alert.title,
            "",
            alert.detail,
            "",
            f"\u67e5\u770b\u8be6\u60c5\uff1a{alert.detail_url}",
        ]
    )
