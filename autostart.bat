@echo off
chcp 65001 > nul
cls

:: ============================================================================
:: IconForge Pro - PowerShell 启动引导 (带日志记录)
::
:: 功能:
::   此脚本尝试启动 setup.ps1，并将自身的执行过程记录到 "autostart_bat_log.txt"。
:: ============================================================================

set "LOG_FILE=%~dp0autostart_bat_log.txt"
set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT_PATH=%SCRIPT_DIR%setup.ps1"

:: 清空旧日志并开始记录
echo [BAT_LOG] ============================================ > "%LOG_FILE%"
echo [BAT_LOG] 启动引导脚本 - 时间: %date% %time% >> "%LOG_FILE%"
echo [BAT_LOG] ============================================ >> "%LOG_FILE%"
echo [BAT_LOG] 脚本目录: %SCRIPT_DIR% >> "%LOG_FILE%"
echo [BAT_LOG] 目标PS1脚本路径: %PS_SCRIPT_PATH% >> "%LOG_FILE%"

if not exist "%PS_SCRIPT_PATH%" (
    echo [BAT_LOG] [FATAL] 致命错误: 未找到 "setup.ps1"！ >> "%LOG_FILE%"
    echo [严重错误] 未在本目录中找到核心管理脚本 "setup.ps1"！
    pause
    exit /b 1
)

echo [BAT_LOG] [INFO] "setup.ps1" 文件已找到。 >> "%LOG_FILE%"
echo [BAT_LOG] [INFO] 准备执行 PowerShell 命令... >> "%LOG_FILE%"

:: 关键命令：执行PowerShell并等待其完成，同时捕获可能的错误输出
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT_PATH%" >> "%LOG_FILE%" 2>&1

:: 检查PowerShell命令本身的执行结果
if %errorlevel% neq 0 (
    echo [BAT_LOG] [ERROR] PowerShell 进程返回了错误代码: %errorlevel%。请检查日志。 >> "%LOG_FILE%"
) else (
    echo [BAT_LOG] [SUCCESS] PowerShell 进程已成功执行并退出。 >> "%LOG_FILE%"
)

echo [BAT_LOG] 引导脚本执行完毕。 >> "%LOG_FILE%"

:: 不再需要 pause 或 exit，让窗口在执行后自然关闭