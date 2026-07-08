from __future__ import annotations

from .config import load_settings
from .feishu import FeishuClient


def main() -> None:
    settings = load_settings()
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    client.send_text_to_chat(
        settings.feishu_chat_id,
        "\u3010\u6d4b\u8bd5\u3011ERP\u8ba2\u5355\u81ea\u52a8\u5316\u98de\u4e66\u63a8\u9001\u5df2\u63a5\u901a",
    )
    print("Feishu test message sent.")


if __name__ == "__main__":
    main()
