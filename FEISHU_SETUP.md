# Feishu Setup

## Required Setup

Create an internal Feishu app in the same enterprise as the target group, enable the app bot, and add the bot to the group.

Store these values only in `.env` or a server secret manager:

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=replace_with_real_secret
FEISHU_CHAT_ID=oc_xxx
```

## Validation

Run:

```bash
python -m src.feishu_test
```

Expected result:

- Console prints `Feishu test message sent.`
- The target Feishu group receives a test message.

## Security

- Do not commit real app secrets.
- Do not commit `.env`.
- Rotate secrets if they were shared in chat or screenshots.
