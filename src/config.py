from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    erp_url: str
    erp_seller_account: str
    erp_phone: str
    erp_password: str
    audit_url: str
    audit_username: str
    audit_password: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_chat_id: str
    cost_feishu_app_id: str
    cost_feishu_app_secret: str
    cost_feishu_chat_id: str
    erp_cost_file: str
    download_dir: Path
    headless: bool


def load_settings() -> Settings:
    download_dir = Path(os.getenv("DOWNLOAD_DIR", "./downloads")).expanduser().resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        erp_url=_required("ERP_URL"),
        erp_seller_account=_required("ERP_SELLER_ACCOUNT"),
        erp_phone=_required("ERP_PHONE"),
        erp_password=_required("ERP_PASSWORD"),
        audit_url=_required("AUDIT_URL"),
        audit_username=_required("AUDIT_USERNAME"),
        audit_password=_required("AUDIT_PASSWORD"),
        feishu_app_id=_required("FEISHU_APP_ID"),
        feishu_app_secret=_required("FEISHU_APP_SECRET"),
        feishu_chat_id=_required("FEISHU_CHAT_ID"),
        cost_feishu_app_id=_optional("COST_FEISHU_APP_ID"),
        cost_feishu_app_secret=_optional("COST_FEISHU_APP_SECRET"),
        cost_feishu_chat_id=_optional("COST_FEISHU_CHAT_ID"),
        erp_cost_file=_optional("ERP_COST_FILE"),
        download_dir=download_dir,
        headless=_bool("HEADLESS", True),
    )
