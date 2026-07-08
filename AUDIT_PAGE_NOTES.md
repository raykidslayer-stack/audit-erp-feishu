# Audit Daily Page Notes

Observed page:

- URL: `https://audit.meelolo.com/daily`
- Page title area: `每日利润与防错雷达`
- Left navigation item: `每日利润与防错雷达`
- Calendar card appears on the left side.
- The selected day has an orange border.
- Upload area text: `点击上传选中日期的 ERP表`
- Native file input button text: `选择文件`
- Submit button text: `提交并清洗预估`
- Example template filename shown on the page: `每日订单_20260623.csv`

Recommended automation sequence:

1. Open `https://audit.meelolo.com/daily`.
2. If redirected to login, log in with the dedicated audit account.
3. Select yesterday's calendar day, because after 00:00 the workflow processes yesterday's orders.
4. Set the ERP export file into `input[type=file]`.
5. Click `提交并清洗预估`.
6. Wait until the page finishes cleaning and estimating.
7. Refresh at 09:00 and read the frontend report data.

Open confirmation items:

- Exact login page placeholders and button text.
- Confirmed: the selected date should be yesterday for production runs.
- Whether the submit action shows a completion toast or changes page data.
- Exact frontend markers for failed ERP upload and suspected loss links.
