# Deployment Status

## Server

- Project directory: `/www/wwwroot/audit-erp-feishu`
- Runtime: server Python under `/www/server/pyporject_evn/versions/`
- Runtime configuration: server `.env`
- Download directory: `/www/wwwroot/audit-erp-feishu/downloads`
- Log directory: `/www/wwwroot/audit-erp-feishu/logs`

## Confirmed

- ERP login works without captcha in the tested account.
- ERP completed-order page is reachable after login.
- Yesterday shipment-time filtering works.
- Export all filtered records and export-record download work.
- Audit login works with the dedicated account.
- Audit daily page upload works with generated `每日订单_YYYYMMDD.csv`.
- Audit submission can have frontend refresh delay, but the calendar turns green after refresh.
- Feishu group robot delivery works.
- Upload success/failure notifications work.
- Daily report extraction from audit frontend works.

## Production Schedule

- 05:00 China time: ERP download and audit upload.
- 09:00 China time: audit daily report to Feishu.
- Optional: periodic alert checks for suspected loss records.

## Operational Notes

- Keep `.env`, `downloads/`, logs, and generated order files out of Git.
- If the audit page shows incorrect table recognition, fix the audit system parser/display logic.
- The automation should be changed only when ERP/audit page structure changes.
