from __future__ import annotations

from .models import AlertItem, AuditSummary, CostReconcileItem, CostReconcileSummary


def render_upload_success(report_date: str, file_name: str) -> str:
    return "\n".join(
        [
            f"ERP订单已提交到audit - {report_date}",
            "",
            "状态：已完成下载、转换并提交清洗",
            f"文件：{file_name}",
            "",
            "说明：audit页面可能有短暂刷新延迟，日历变绿后即代表清洗完成。",
        ]
    )


def render_upload_failure(report_date: str, error: str) -> str:
    return "\n".join(
        [
            f"ERP订单上传疑似失败 - {report_date}",
            "",
            "状态：自动化流程执行失败",
            f"错误：{error}",
            "",
            "请检查ERP下载、audit上传页面或服务器日志。",
        ]
    )


def render_daily_report(summary: AuditSummary) -> str:
    return "\n".join(
        [
            f"audit每日利润日报 - {summary.report_date}",
            "",
            "核心指标：",
            f"发货单量：{summary.total_orders}",
            f"昨日预估利润：{summary.current_profit or '-'}",
            f"昨日预估应收：{summary.daily_revenue or '-'}",
            f"昨日预估货本：{summary.daily_goods_cost or '-'}",
            f"昨日预估平台费：{summary.daily_platform_fee or '-'}",
            f"昨日预估运费：{summary.daily_shipping_fee or '-'}",
            f"昨日预估投流费：{summary.daily_ad_spend or '-'}",
            f"本月动态累计：{summary.monthly_profit or '-'}",
            "",
            "本月预估动态累加：",
            f"本月预估累计应收：{summary.revenue or '-'}",
            f"本月预估累计货本：{summary.goods_cost or '-'}",
            f"本月预估累计平台费：{summary.platform_fee or '-'}",
            f"本月预估累计运费：{summary.shipping_fee or '-'}",
            f"本月预估累计投流费：{summary.ad_spend or '-'}",
            "",
            "异常提醒：",
            f"疑似亏损订单：{summary.suspected_loss_links}",
            "",
            f"查看详情：{summary.detail_url}",
        ]
    )


def render_alert(alert: AlertItem) -> str:
    return "\n".join(
        [
            alert.title,
            "",
            alert.detail,
            "",
            f"查看详情：{alert.detail_url}",
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

    source = "audit 后端对账接口" if summary.source == "audit" else "本地 ERP 成本表 + audit 成本库接口"
    lines = [
        f"ERP vs audit 成本库核查 - {summary.report_date}",
        "",
        "核查口径：先核对品名，再核对成本；每条异常明确处理系统。",
        f"数据来源：{source}",
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
            f"- ERP 有 / audit 无：{summary.audit_missing_count} 个 -> 去 audit 补品名和成本",
            f"- audit 有 / ERP 无：{summary.erp_missing_count} 个 -> 确认停用；仍在售则去 ERP 补",
            f"- 品名不完全一致：{summary.name_mismatch_count} 个 -> 统一品名或维护映射",
            f"- audit 成本缺失/为 0：{summary.audit_cost_missing_count} 个 -> 去 audit 补成本",
            f"- ERP 成本缺失/为 0：{summary.erp_cost_missing_count} 个 -> 去 ERP 补成本",
            f"- 双方成本不一致：{summary.cost_mismatch_count} 个 -> 财务确认基准价",
            f"- 重复品名：{summary.duplicate_count} 个 -> 先合并或区分重复品名",
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
