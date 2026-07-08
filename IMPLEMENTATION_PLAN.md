# Implementation Plan

## Confirmed Schedule

- 05:00: download yesterday's completed ERP orders and upload them to audit.
- 09:00: read audit frontend data and send the Feishu group report.

## ERP Flow

1. Open the completed-order page.
2. If redirected to login, sign in and open the completed-order page again.
3. Do not click the top status warning tabs because they add filters.
4. Select yesterday in the shipment-time date picker.
5. Click filter.
6. Hover/click export and choose all filtered data.
7. Confirm the default export settings.
8. Open export records and download the latest export.

## File Handling

1. Keep the original ERP `.xlsx` export.
2. Generate `每日订单_YYYYMMDD.csv`.
3. Upload the generated CSV to audit.

## Audit Flow

1. Open `/daily`.
2. Login if needed.
3. Select yesterday in the calendar.
4. Upload the generated CSV.
5. Click `提交并清洗预估`.
6. Treat frontend green status as success after refresh.

## Feishu Messages

- Upload success: sent after the 05:00 workflow completes.
- Upload failure: sent if the automation throws an error.
- Daily report: sent at 09:00 with audit frontend metrics.
- Alert checks: can be run periodically for suspected loss records.

## Known Limitation

Audit table recognition/display issues belong to the audit system parser and should be fixed there.
