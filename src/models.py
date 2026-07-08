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
