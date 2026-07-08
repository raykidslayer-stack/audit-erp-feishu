from __future__ import annotations

import json
import time
from dataclasses import dataclass

import requests


FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"


@dataclass
class TokenCache:
    value: str | None = None
    expires_at: float = 0


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self._token = TokenCache()

    def tenant_access_token(self) -> str:
        now = time.time()
        if self._token.value and self._token.expires_at - now > 120:
            return self._token.value

        response = requests.post(
            f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu token request failed: {data}")

        self._token.value = data["tenant_access_token"]
        self._token.expires_at = now + int(data.get("expire", 7200))
        return self._token.value

    def send_text_to_chat(self, chat_id: str, text: str) -> dict:
        return self._send_message(chat_id, "chat_id", "text", {"text": text})

    def send_card_to_chat(self, chat_id: str, card: dict) -> dict:
        return self._send_message(chat_id, "chat_id", "interactive", card)

    def _send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: dict,
    ) -> dict:
        response = requests.post(
            f"{FEISHU_BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers={"Authorization": f"Bearer {self.tenant_access_token()}"},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu message send failed: {data}")
        return data

