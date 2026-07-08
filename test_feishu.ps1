$ErrorActionPreference = "Stop"

$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $Project ".env"

if (-not (Test-Path $EnvFile)) {
    throw "Missing .env file: $EnvFile"
}

$Vars = @{}
Get-Content -Path $EnvFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        $Vars[$matches[1]] = $matches[2]
    }
}

$TokenBody = @{
    app_id = $Vars["FEISHU_APP_ID"]
    app_secret = $Vars["FEISHU_APP_SECRET"]
} | ConvertTo-Json -Compress

$TokenResp = Invoke-RestMethod `
    -Method Post `
    -Uri "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" `
    -ContentType "application/json" `
    -Body $TokenBody

if ($TokenResp.code -ne 0) {
    throw "Feishu token request failed: $($TokenResp | ConvertTo-Json -Compress)"
}

$Content = @{
    text = "ERP订单上传日报测试`n飞书群推送链路已接通。"
} | ConvertTo-Json -Compress

$MessageBody = @{
    receive_id = $Vars["FEISHU_CHAT_ID"]
    msg_type = "text"
    content = $Content
} | ConvertTo-Json -Compress

$MessageResp = Invoke-RestMethod `
    -Method Post `
    -Uri "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id" `
    -Headers @{ Authorization = "Bearer $($TokenResp.tenant_access_token)" } `
    -ContentType "application/json; charset=utf-8" `
    -Body $MessageBody

if ($MessageResp.code -ne 0) {
    throw "Feishu message send failed: $($MessageResp | ConvertTo-Json -Compress)"
}

Write-Host "Feishu test message sent successfully."
