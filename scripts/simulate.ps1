# .\scripts\simulate.ps1 overheat -Sensor sensor-1
# Scenarios: overheat, offline, pollution (per sensor), api-errors, crash,
# down/up (stop/start the container), reset, status
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("overheat", "offline", "pollution", "api-errors", "crash", "down", "up", "reset", "status")]
    [string]$Scenario,
    [string]$Sensor = "sensor-1",
    [string]$Url = "http://localhost:8000"
)

switch ($Scenario) {
    "down"   { docker stop sensor-dashboard; "Container stopped. SensorDashboardDown should fire in about 40 seconds." }
    "up"     { docker start sensor-dashboard; "Container started. The alert resolves within about 30 seconds." }
    "status" { Invoke-RestMethod "$Url/api/simulation" | ConvertTo-Json -Depth 4 }
    default {
        $body = @{ active = $true }
        if ($Scenario -in @("overheat", "offline", "pollution")) { $body.sensor = $Sensor }
        Invoke-RestMethod -Method Post -Uri "$Url/api/simulate/$Scenario" `
            -ContentType "application/json" -Body ($body | ConvertTo-Json) | ConvertTo-Json
    }
}
