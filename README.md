# Audit ERP Feishu Automation

Daily automation for exporting completed ERP orders, uploading them into the audit daily profit page, and sending Feishu group notifications.

## Current Status

- ERP completed-order export is working.
- ERP `.xlsx` exports are converted to `每日订单_YYYYMMDD.csv` for audit upload.
- Audit upload and `提交并清洗预估` submission are working.
- Feishu upload success/failure messages are working.
- Feishu daily profit report messages are working.
- Audit frontend refresh can lag behind backend cleaning, so green calendar status may appear after a manual or automatic refresh.

## Workflow

- 05:00 China time: download yesterday's completed ERP orders and upload them to audit.
- After upload: send a Feishu message for success or failure.
- 09:00 China time: read the audit frontend report and send the daily Feishu report.
- Alert checks can be run separately for suspected loss or red-status reminders.
- Cost reconciliation can be run separately. It checks ERP product names/costs against the
  audit cost library and sends an actionable Feishu list that says whether to fix ERP,
  fix audit, or maintain a name mapping.

## Required Environment Variables

Copy `.env.example` to `.env` on the server and fill in the real values there.

Do not commit real usernames, passwords, app secrets, cookies, or downloaded order files.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run

Run the download and upload workflow:

```bash
python -m src.workflow run-download-upload
```

Run a backfill:

```bash
python -m src.workflow run-download-upload --start-date 2026-07-07 --end-date 2026-07-07
```

Run only the Feishu daily report:

```bash
python -m src.workflow report
```

Run only alert checks:

```bash
python -m src.workflow alerts
```

Run ERP vs audit cost reconciliation:

```bash
python -m src.workflow cost-reconcile
```

Cost reconciliation first tries `AUDIT_URL`'s `/api/cost_reconcile` endpoint. If audit
does not provide that endpoint yet, set `ERP_COST_FILE` to the latest ERP product cost
export. The local fallback reads audit costs from `/api/cost_validate`, reads the ERP
file, and classifies issues as:

- ERP has product / audit missing: fix audit.
- audit has product / ERP missing: confirm inactive or fix ERP.
- Product names differ after matching: standardize names or maintain mapping.
- audit cost missing or zero: fix audit.
- ERP cost missing or zero: fix ERP.
- Both have costs but values differ: finance confirms the baseline cost.

Use `COST_FEISHU_APP_ID`, `COST_FEISHU_APP_SECRET`, and `COST_FEISHU_CHAT_ID` for the
cost-check group. Do not reuse the ERP order report group unless that is intentional.

## Suggested Schedule

Use cron, Baota scheduled tasks, systemd timers, or another server scheduler.

```cron
0 5 * * * cd /www/wwwroot/audit-erp-feishu && TZ=Asia/Shanghai /path/to/python -m src.workflow run-download-upload
0 9 * * * cd /www/wwwroot/audit-erp-feishu && TZ=Asia/Shanghai /path/to/python -m src.workflow report
0 10 */10 * * cd /www/wwwroot/audit-erp-feishu && TZ=Asia/Shanghai /path/to/python -m src.workflow cost-reconcile
*/10 * * * * cd /www/wwwroot/audit-erp-feishu && TZ=Asia/Shanghai /path/to/python -m src.workflow alerts
```

## Notes

- The raw ERP export is kept in `downloads/`.
- The audit upload file is generated beside it as `每日订单_YYYYMMDD.csv`.
- If audit table recognition is wrong, fix the audit system parser/display logic rather than the ERP download workflow.
