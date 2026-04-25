Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$reportsDir = Join-Path $repoRoot "reports"
$reportPath = Join-Path $reportsDir "skill-test-report.json"
$python = [string](Get-Command python -CommandType Application | Select-Object -First 1 -ExpandProperty Source)
$validator = "C:\Users\13754\.codex\skills\.system\skill-creator\scripts\quick_validate.py"

if (-not (Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir | Out-Null
}

function Invoke-TestStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter()]
        [string[]]$ArgumentList = @(),

        [Parameter()]
        [string]$WorkingDirectory = $repoRoot
    )

    $startedAt = Get-Date
    $stdoutLines = @()
    $stderrLines = @()
    $exitCode = 0

    Push-Location $WorkingDirectory
    try {
        $nativePreferenceWasPresent = Test-Path variable:PSNativeCommandUseErrorActionPreference
        if ($nativePreferenceWasPresent) {
            $previousNativePreference = $PSNativeCommandUseErrorActionPreference
            $PSNativeCommandUseErrorActionPreference = $false
        }

        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"

        $combinedOutput = & $FilePath @ArgumentList 2>&1
        if ($null -ne $LASTEXITCODE) {
            $exitCode = $LASTEXITCODE
        }
    } finally {
        if ($nativePreferenceWasPresent) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }

    foreach ($entry in @($combinedOutput)) {
        if ($entry -is [System.Management.Automation.ErrorRecord]) {
            $stderrLines += $entry.ToString()
        } elseif ($null -ne $entry) {
            $stdoutLines += $entry.ToString()
        }
    }

    $stdout = ($stdoutLines -join [Environment]::NewLine).Trim()
    $stderr = ($stderrLines -join [Environment]::NewLine).Trim()
    $finishedAt = Get-Date

    return [pscustomobject]@{
        name = $Name
        command = @($FilePath) + $ArgumentList
        working_directory = $WorkingDirectory
        exit_code = $exitCode
        passed = ($exitCode -eq 0)
        started_at = $startedAt.ToString("s")
        finished_at = $finishedAt.ToString("s")
        duration_ms = [int][Math]::Round(($finishedAt - $startedAt).TotalMilliseconds)
        stdout = $stdout.Trim()
        stderr = $stderr.Trim()
    }
}

$skills = @(
    @{
        name = "goofish-attached-collector"
        path = "skills/goofish-attached-collector"
        smoke = @("skills/goofish-attached-collector/scripts/check_attached_collector.py")
    },
    @{
        name = "goofish-pricing-cleaner"
        path = "skills/goofish-pricing-cleaner"
        smoke = @(
            "skills/goofish-pricing-cleaner/scripts/clean_pricing.py",
            "apple watch ultra 2",
            "--include", "ultra 2",
            "--include", "ultra2",
            "--exclude", "box",
            "--exclude", "gen1",
            "--exclude", "ultra 3",
            "--min-price", "2000",
            "--max-price", "5000"
        )
    },
    @{
        name = "goofish-spec-enrichment"
        path = "skills/goofish-spec-enrichment"
        smoke = @(
            "skills/goofish-spec-enrichment/scripts/run_enrichment.py",
            "--business-domain", "apple_m_series",
            "--limit", "1",
            "--no-use-llm"
        )
    },
    @{
        name = "goofish-buy-zone-analysis"
        path = "skills/goofish-buy-zone-analysis"
        smoke = @(
            "skills/goofish-buy-zone-analysis/scripts/buy_zone.py",
            "apple watch ultra 2",
            "--include", "ultra 2",
            "--include", "ultra2",
            "--exclude", "box",
            "--exclude", "gen1",
            "--exclude", "ultra 3",
            "--min-price", "2000",
            "--max-price", "5000"
        )
    },
    @{
        name = "goofish-server-deploy"
        path = "skills/goofish-server-deploy"
        smoke = @("skills/goofish-server-deploy/scripts/check_deploy.py")
    },
    @{
        name = "repo-module-doc-writer"
        path = "skills/repo-module-doc-writer"
        smoke = @("skills/repo-module-doc-writer/scripts/audit_docs.py")
    },
    @{
        name = "tavily-research"
        path = "skills/tavily-research"
        smoke = @(
            "skills/tavily-research/scripts/tavily_search.py",
            "Apple Watch Ultra 2 used price",
            "--topic", "general",
            "--max-results", "3",
            "--include-answer"
        )
    }
)

$results = New-Object System.Collections.Generic.List[object]

$results.Add(
    (Invoke-TestStep -Name "compileall-skills" -FilePath $python -ArgumentList @("-m", "compileall", "skills"))
)

foreach ($skill in $skills) {
    $results.Add(
        (Invoke-TestStep -Name ("validate-" + $skill.name) -FilePath $python -ArgumentList @(
            $validator,
            (Join-Path $repoRoot $skill.path)
        ))
    )

    $smokeArgs = @($skill.smoke[0])
    if ($skill.smoke.Count -gt 1) {
        $smokeArgs += $skill.smoke[1..($skill.smoke.Count - 1)]
    }

    $results.Add(
        (Invoke-TestStep -Name ("smoke-" + $skill.name) -FilePath $python -ArgumentList $smokeArgs)
    )
}

$report = [pscustomobject]@{
    generated_at = (Get-Date).ToString("s")
    repo_root = $repoRoot
    summary = [pscustomobject]@{
        total = $results.Count
        passed = @($results | Where-Object { $_.passed }).Count
        failed = @($results | Where-Object { -not $_.passed }).Count
    }
    results = $results
}

$report | ConvertTo-Json -Depth 6 | Set-Content -Path $reportPath -Encoding UTF8

$failed = @($results | Where-Object { -not $_.passed })
foreach ($result in $results) {
    $status = if ($result.passed) { "PASS" } else { "FAIL" }
    Write-Host ("[{0}] {1}" -f $status, $result.name)
}

Write-Host ("Report: {0}" -f $reportPath)

if ($failed.Count -gt 0) {
    exit 1
}
