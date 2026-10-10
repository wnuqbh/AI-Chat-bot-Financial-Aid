# End-to-end check against a running backend, including a real Gemini call.
# Usage (server must be running):  .\scripts\smoke_test.ps1
param([string]$BaseUrl = "http://127.0.0.1:5000/api")

$ErrorActionPreference = "Stop"
$failures = 0

function Check($name, [scriptblock]$test) {
    try {
        $detail = & $test
        Write-Host "PASS  $name" -ForegroundColor Green
        if ($detail) { Write-Host "      $detail" -ForegroundColor DarkGray }
    } catch {
        $script:failures++
        Write-Host "FAIL  $name" -ForegroundColor Red
        Write-Host "      $($_.Exception.Message)" -ForegroundColor DarkGray
        if ($_.ErrorDetails.Message) { Write-Host "      $($_.ErrorDetails.Message)" -ForegroundColor DarkGray }
    }
}

function Expect-Status($expected, [scriptblock]$request) {
    try { & $request | Out-Null } catch {
        $actual = [int]$_.Exception.Response.StatusCode
        if ($actual -eq $expected) { return "got $actual as expected" }
        throw "expected $expected, got $actual"
    }
    throw "expected $expected, but the request succeeded"
}

function Post($path, $body, $headers = @{}) {
    Invoke-RestMethod -Method Post "$BaseUrl$path" -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json)
}

# A fresh user each run, so the script can be re-run without "email already registered".
$email = "smoke-$(Get-Date -Format 'yyyyMMddHHmmss')@example.com"
$password = "password123"

Check "Server is up" { (Invoke-RestMethod "$BaseUrl/health").status }

Check "Register" {
    $r = Post "/auth/register" @{ email = $email; password = $password }
    $script:headers = @{ Authorization = "Bearer $($r.access_token)" }
    $r.user.email
}

Check "Login" { Post "/auth/login" @{ email = $email; password = $password } | Out-Null; "token issued" }

Check "Add holdings" {
    Post "/portfolio/holding" @{ symbol = "VTI"; quantity = "10"; average_cost = "220" } $headers | Out-Null
    Post "/portfolio/holding" @{ symbol = "AAPL"; quantity = "5"; average_cost = "180" } $headers | Out-Null
    ((Invoke-RestMethod "$BaseUrl/portfolio/" -Headers $headers).portfolio.holdings.symbol) -join ", "
}

Check "Chat with Gemini" {
    $s = Post "/chat/session" @{ title = "Smoke test" } $headers
    $script:conversationId = $s.conversation_id
    $reply = Post "/chat/message" @{ conversation_id = $conversationId; content = "Briefly: is my portfolio diversified?" } $headers
    $text = $reply.assistant_message.content
    $text.Substring(0, [Math]::Min(200, $text.Length)) + "..."
}

Check "Chat history is saved" {
    $count = (Invoke-RestMethod "$BaseUrl/chat/history/$conversationId" -Headers $headers).messages.Count
    if ($count -ne 2) { throw "expected 2 messages, found $count" }
    "$count messages"
}

Check "Rejects missing token (401)" { Expect-Status 401 { Invoke-RestMethod "$BaseUrl/portfolio/" } }
Check "Rejects non-admin (403)" { Expect-Status 403 { Invoke-RestMethod "$BaseUrl/admin/users" -Headers $headers } }
Check "Rejects wrong password (401)" { Expect-Status 401 { Post "/auth/login" @{ email = $email; password = "wrong" } } }

Write-Host ""
if ($failures -eq 0) {
    Write-Host "All checks passed." -ForegroundColor Green
} else {
    Write-Host "$failures check(s) failed. See the server window for details." -ForegroundColor Red
    exit 1
}
