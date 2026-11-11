# 测试通过后安装（Windows）：工具 + Clash 侧配置
#   bin/            → %LOCALAPPDATA%\clash-pooling\bin
#   lib/clashctl/   → %LOCALAPPDATA%\clash-pooling\lib\clashctl
#   clash/          → Clash 配置目录（保留已有清单）
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA 'clash-pooling'

Write-Host '== 1. 测试 =='
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tests\run.ps1')
if ($LASTEXITCODE -ne 0) { Write-Host '测试未通过，中止安装' -ForegroundColor Red; exit 1 }

Write-Host ''
Write-Host '== 2. 安装 =='
New-Item -ItemType Directory -Force -Path (Join-Path $dest 'bin') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dest 'lib') | Out-Null
Copy-Item (Join-Path $root 'bin\*') (Join-Path $dest 'bin') -Force
if (Test-Path (Join-Path $dest 'lib\clashctl')) {
    Remove-Item (Join-Path $dest 'lib\clashctl') -Recurse -Force
}
Copy-Item (Join-Path $root 'lib\clashctl') (Join-Path $dest 'lib') -Recurse -Force
Get-ChildItem (Join-Path $dest 'lib') -Recurse -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
[IO.File]::WriteAllText((Join-Path $dest 'lib\clashctl\.project_root'), $root, [Text.UTF8Encoding]::new($false))
Write-Host "  $dest\bin\clashctl.cmd"
Write-Host "  $dest\lib\clashctl"

Write-Host ''
Write-Host '== 3. 加入 PATH =='
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$binPath = Join-Path $dest 'bin'
if ($userPath -notlike "*$binPath*") {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$binPath", 'User')
    Write-Host "  已加入用户 PATH（重开终端生效）：$binPath"
} else {
    Write-Host "  已在 PATH 中：$binPath"
}

Write-Host ''
Write-Host '== 4. 同步 Clash 配置 =='
& (Join-Path $binPath 'clashctl.cmd') sync

Write-Host ''
Write-Host '== 5. 自检 =='
& (Join-Path $binPath 'clashctl.cmd') auto status
Write-Host ''
Write-Host '== 6. 环境诊断 =='
& (Join-Path $binPath 'clashctl.cmd') doctor
