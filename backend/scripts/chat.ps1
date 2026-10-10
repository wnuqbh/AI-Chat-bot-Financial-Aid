# Interactive chat with the advisor from the terminal (until the frontend exists).
# Usage (server must be running):  .\scripts\chat.ps1
param([string]$BaseUrl = "http://127.0.0.1:5000/api")

$ErrorActionPreference = "Stop"

function Post($path, $body, $headers = @{}) {
    Invoke-RestMethod -Method Post "$BaseUrl$path" -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json)
}

function Show-Error($err) {
    $message = $err.ErrorDetails.Message
    if ($message) {
        try { $message = ($message | ConvertFrom-Json).error } catch {}
    } else {
        $message = $err.Exception.Message
    }
    Write-Host "Error: $message" -ForegroundColor Red
}

# Log in, or register if the account doesn't exist yet.
$email = Read-Host "Email"
$securePassword = Read-Host "Password (8+ characters)" -AsSecureString
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))

try {
    $auth = Post "/auth/login" @{ email = $email; password = $password }
    Write-Host "Logged in." -ForegroundColor Green
} catch {
    if ([int]$_.Exception.Response.StatusCode -ne 401) { Show-Error $_; exit 1 }
    $answer = Read-Host "Login failed. Register a new account with this email? (y/n)"
    if ($answer -ne "y") { exit 1 }
    try {
        $auth = Post "/auth/register" @{ email = $email; password = $password }
        Write-Host "Account created." -ForegroundColor Green
    } catch { Show-Error $_; exit 1 }
}
$headers = @{ Authorization = "Bearer $($auth.access_token)" }

$conversationId = (Post "/chat/session" @{ title = "Terminal chat" } $headers).conversation_id

Write-Host ""
Write-Host "Ask anything. Commands: /add SYMBOL QUANTITY AVG_COST   /portfolio   /new   /quit" -ForegroundColor DarkGray
Write-Host ""

while ($true) {
    $text = Read-Host "You"
    if (-not $text.Trim()) { continue }

    try {
        switch -Regex ($text.Trim()) {
            '^/quit$' { exit 0 }
            '^/new$' {
                $conversationId = (Post "/chat/session" @{ title = "Terminal chat" } $headers).conversation_id
                Write-Host "Started a new conversation." -ForegroundColor DarkGray
                break
            }
            '^/portfolio$' {
                $holdings = (Invoke-RestMethod "$BaseUrl/portfolio/" -Headers $headers).portfolio.holdings
                if (-not $holdings) { Write-Host "No holdings yet. Add one with /add VTI 10 220" -ForegroundColor DarkGray }
                else { $holdings | Format-Table symbol, quantity, average_cost | Out-Host }
                break
            }
            '^/add\s+(\S+)\s+(\S+)\s+(\S+)$' {
                $h = (Post "/portfolio/holding" @{ symbol = $Matches[1]; quantity = $Matches[2]; average_cost = $Matches[3] } $headers).holding
                Write-Host "Added $($h.symbol)." -ForegroundColor DarkGray
                break
            }
            '^/' { Write-Host "Unknown command." -ForegroundColor DarkGray; break }
            default {
                Write-Host "Advisor is thinking..." -ForegroundColor DarkGray
                $reply = Post "/chat/message" @{ conversation_id = $conversationId; content = $text } $headers
                Write-Host ""
                Write-Host "Advisor: $($reply.assistant_message.content)" -ForegroundColor Cyan
                Write-Host ""
            }
        }
    } catch {
        Show-Error $_
    }
}
