from __future__ import annotations

from .models import AlertItem, AuditSummary, CostReconcileItem, CostReconcileSummary


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
            f"\u6628\u65e5\u9884\u4f30\u5229\u6da6\uff1a{summary.current_profit or '-'}",
            f"\u6628\u65e5\u9884\u4f30\u5e94\u6536\uff1a{summary.daily_revenue or '-'}",
            f"\u6628\u65e5\u9884\u4f30\u8d27\u672c\uff1a{summary.daily_goods_cost or '-'}",
            f"\u6628\u65e5\u9884\u4f30\u5e73\u53f0\u8d39\uff1a{summary.daily_platform_fee or '-'}",
            f"\u6628\u65e5\u9884\u4f30\u8fd0\u8d39\uff1a{summary.daily_shipping_fee or '-'}",
            f"\u6628\u65e5\u9884\u4f30\u6295\u6d41\u8d39\uff1a{summary.daily_ad_spend or '-'}",
            f"\u672c\u6708\u52a8\u6001\u7d2f\u8ba1\uff1a{summary.monthly_profit or '-'}",
            "",
            "\u672c\u6708\u9884\u4f30\u52a8\u6001\u7d2f\u52a0\uff1a",
            f"\u672c\u6708\u9884\u4f30\u7d2f\u8ba1\u5e94\u6536\uff1a{summary.revenue or '-'}",
            f"\u672c\u6708\u9884\u4f30\u7d2f\u8ba1\u8d27\u672c\uff1a{summary.goods_cost or '-'}",
            f"\u672c\u6708\u9884\u4f30\u7d2f\u8ba1\u5e73\u53f0\u8d39\uff1a{summary.platform_fee or '-'}",
            f"\u672c\u6708\u9884\u4f30\u7d2f\u8ba1\u8fd0\u8d39\uff1a{summary.shipping_fee or '-'}",
            f"\u672c\u6708\u9884\u4f30\u7d2f\u8ba1\u6295\u6d41\u8d39\uff1a{summary.ad_spend or '-'}",
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


def render_cost_reconcile(summary: CostReconcileSummary) -> str:
    if summary.status != "success":
        return "\n".join(
            [
                f"ERP vs audit 成本库核查 - {summary.report_date}",
                "",
                "状态：未完成",
                f"原因：{summary.error or '缺少必要数据'}",
                "",
                "处理建议：先提供最新 ERP 成本表，或在 audit 后端上线 /api/cost_reconcile。",
            ]
        )

    lines = [
        f"ERP vs audit 成本库核查 - {summary.report_date}",
        "",
        "核查口径：先核对品名，再核对成本；每条异常明确处理系统。",
        f"数据来源：{'audit 后端对账接口' if summary.source == 'audit' else '本地 ERP 成本表 + audit 成本库接口'}",
        f"audit 品名数：{summary.audit_count}",
        f"ERP 品名数：{summary.erp_count}",
        f"异常总数：{summary.total_issues}",
    ]
    if summary.stale_erp_file:
        lines.extend(["", "提醒：ERP 成本表超过 30 天未更新，建议重新导出后再核查。"])

    lines.extend(
        [
            "",
            "异常分类：",
            f"- ERP 有 / audit 无：{summary.audit_missing_count} 个 → 去 audit 补品名和成本",
            f"- audit 有 / ERP 无：{summary.erp_missing_count} 个 → 确认停用；仍在售则去 ERP 补",
            f"- 品名不完全一致：{summary.name_mismatch_count} 个 → 统一品名或维护映射",
            f"- audit 成本缺失/为 0：{summary.audit_cost_missing_count} 个 → 去 audit 补成本",
            f"- ERP 成本缺失/为 0：{summary.erp_cost_missing_count} 个 → 去 ERP 补成本",
            f"- 双方成本不一致：{summary.cost_mismatch_count} 个 → 财务确认基准价",
            f"- 重复品名：{summary.duplicate_count} 个 → 先合并或区分重复品名",
        ]
    )

    items = summary.items or []
    if items:
        lines.extend(["", "优先处理明细："])
        for item in items[:20]:
            lines.append(_render_cost_reconcile_item(item))
        if len(items) > 20:
            lines.append(f"... 其余 {len(items) - 20} 条请进入 audit 查看/导出。")
    else:
        lines.extend(["", "结论：ERP 与 audit 品名和成本均已对上。"])

    if summary.detail_url:
        lines.extend(["", f"查看详情：{summary.detail_url}"])
    return "\n".join(lines)


def _render_cost_reconcile_item(item: CostReconcileItem) -> str:
    name = item.erp_name or item.audit_name or "-"
    if item.erp_name and item.audit_name and item.erp_name != item.audit_name:
        name = f"ERP「{item.erp_name}」/ audit「{item.audit_name}」"

    costs = []
    if item.erp_cost:
        costs.append(f"ERP {item.erp_cost}")
    if item.audit_cost:
        costs.append(f"audit {item.audit_cost}")
    if item.diff:
        costs.append(f"差额 {item.diff}")
    cost_text = f"（{', '.join(costs)}）" if costs else ""
    return f"- {name}{cost_text}：{item.action}"
