@echo off
rem clashctl 启动器（Windows）：找到 Python 后运行同目录的 clashctl 脚本
setlocal
set "HERE=%~dp0"
set "PY="

if defined CLASHCTL_PYTHON set "PY=%CLASHCTL_PYTHON%"
if not defined PY (
  for %%P in (python.exe python3.exe) do (
    if not defined PY (
      where %%P >nul 2>nul && set "PY=%%P"
    )
  )
)
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
)
if not defined PY (
  echo 找不到 Python，请先安装 Python 3.10+ 或设置 CLASHCTL_PYTHON 环境变量 1>&2
  exit /b 1
)

"%PY%" "%HERE%clashctl" %*
