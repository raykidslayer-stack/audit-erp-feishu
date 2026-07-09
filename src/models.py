from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditSummary:
    report_date: str
    total_orders: int
    successful_orders: int
    failed_orders: int
    suspected_loss_links: int
    detail_url: str
    current_profit: str = ""
    daily_revenue: str = ""
    daily_goods_cost: str = ""
    daily_platform_fee: str = ""
    daily_shipping_fee: str = ""
    daily_ad_spend: str = ""
    monthly_profit: str = ""
    revenue: str = ""
    goods_cost: str = ""
    platform_fee: str = ""
    shipping_fee: str = ""
    ad_spend: str = ""

    @property
    def success_rate(self) -> str:
        if self.total_orders == 0:
            return "0.0%"
        return f"{self.successful_orders / self.total_orders * 100:.1f}%"


@dataclass(frozen=True)
class AlertItem:
    alert_type: str
    title: str
    detail: str
    detail_url: str
    dedupe_key: str


@dataclass(frozen=True)
class DownloadResult:
    file_path: Path
    order_date: str


@dataclass(frozen=True)
class CostReconcileItem:
    issue_type: str
    action: str
    erp_name: str = ""
    audit_name: str = ""
    erp_cost: str = ""
    audit_cost: str = ""
    diff: str = ""
    note: str = ""


@dataclass(frozen=True)
class CostReconcileSummary:
    report_date: str
    source: str
    status: str
    audit_count: int = 0
    erp_count: int = 0
    total_issues: int = 0
    audit_missing_count: int = 0
    erp_missing_count: int = 0
    name_mismatch_count: int = 0
    audit_cost_missing_count: int = 0
    erp_cost_missing_count: int = 0
    cost_mismatch_count: int = 0
    duplicate_count: int = 0
    stale_erp_file: bool = False
    detail_url: str = ""
    items: list[CostReconcileItem] | None = None
    error: str = ""
