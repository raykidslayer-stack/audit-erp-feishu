# ERP Completed Orders Page Notes

Observed page:

- Direct URL: `https://erp.huice.com/#/app/order/list/t/8`
- This URL opens the completed-order page directly.
- ERP login does not require captcha.
- After login, ERP does not automatically return to the completed-order page, so the automation must navigate to the direct URL again.
- The login page requires accepting the agreement checkbox before clicking `登录`.
- Top status/warning tabs must stay clear. Do not click them, because they immediately add filters.
- A clicked status/warning tab has a blue border.
- The date filter used for the workflow is shipment time.
- Yesterday should be entered as:
  - start: `YYYY-MM-DD 00:00:00`
  - end: `YYYY-MM-DD 23:59:59`
- The query button text is `筛选`.
- Export menu is on the right side of the table toolbar.
- Use `导出全部筛选数据`, not selected-row export.
- Export settings do not need changes. Click `确认`.
- Wait about 10 seconds for the async export task.
- Open `查看导出记录`.
- In the export records drawer, click the right-side `下载` action once status is `导出完成`.
- Export records usually only show the current export task, and the first row is the current task.

Recommended automation sequence:

1. Open `https://erp.huice.com/#/app/order/list/t/8`.
2. If redirected to login, log in with account, phone, password, and the agreement checkbox.
3. After login, navigate to the completed-order URL again.
4. Keep all status/warning tabs untouched.
5. Fill yesterday's shipment-time range.
6. Click `筛选`.
7. Click `导出`.
8. Click `导出全部筛选数据`.
9. Click `确认`.
10. Wait about 10 seconds.
11. Click `查看导出记录`.
12. Click `下载` in the first completed export row.

Open confirmation items:

- Exact ERP login input attributes if positional input filling is not stable.
- Whether the server login will require trusted-device confirmation or IP whitelist.
- Confirmed: no captcha is expected.
- Confirmed: the first export-record row is generally the current task.
