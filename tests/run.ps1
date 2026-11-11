# 运行全部测试（PowerShell 版）
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$fail = 0

function Find-Python {
    if ($env:CLASHCTL_PYTHON) { return $env:CLASHCTL_PYTHON }
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
                     "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$py = Find-Python
if (-not $py) { Write-Host '找不到 Python，无法运行测试'; exit 1 }

Write-Host '== 分组与规则 =='
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    & node tests\groups.test.cjs
    if ($LASTEXITCODE -ne 0) { $fail = 1 }
} else {
    Write-Host '  跳过：未安装 Node.js（该测试需要执行 Script.js 的 JS 逻辑）'
}

Write-Host ''
Write-Host '== 清单与增量刷新 =='
& $py tests\manifest.test.py
if ($LASTEXITCODE -ne 0) { $fail = 1 }

Write-Host ''
Write-Host '== 敏感内容 =='
& $py tests\check_sensitive.py
if ($LASTEXITCODE -ne 0) { $fail = 1 }

Write-Host ''
if ($fail -eq 0) { Write-Host '全部通过' } else { Write-Host '有失败项' }
exit $fail
