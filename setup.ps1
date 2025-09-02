# ============================================================================
# IconForge Pro - 终极部署与启动器 (PowerShell 单文件版)
# 版本: 3.3 (逻辑注释优化)
#
# 更新日志:
#   - 优化了启动主程序代码块的注释，清晰地解释了为什么在
#     启动前需要激活虚拟环境，以消除关于重复操作的疑虑。
# ============================================================================

# --- 动态路径和日志文件设置 ---
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$logFile = Join-Path $scriptDir "setup_ps1_log.txt"

# --- 日志记录函数 ---
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    Add-Content -Path $logFile -Value $logEntry
    Write-Host $logEntry
}

# --- 清空旧日志并开始记录 ---
if (Test-Path $logFile) { Clear-Content -Path $logFile -ErrorAction SilentlyContinue }
Write-Log "====================================================="
Write-Log "PowerShell 脚本启动 (版本 3.3 - 逻辑注释优化)"
Write-Log "====================================================="
Write-Log "脚本目录: $scriptDir"

# --- 自动请求管理员权限 ---
Write-Log "检查管理员权限..."
$currentUser = New-Object Security.Principal.WindowsPrincipal $([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentUser.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Log "当前用户非管理员，尝试以管理员权限重新启动..." -Level "WARN"
    try {
        $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($myInvocation.mycommand.definition)`""
        Start-Process powershell -Verb runAs -ArgumentList $arguments -ErrorAction Stop
        Write-Log "成功发出管理员权限请求。当前非管理员脚本将退出。"
    } catch {
        Write-Log "请求管理员权限失败！异常: $($_.Exception.Message)" -Level "FATAL"
        Read-Host "按回车键退出"
    }
    exit
}
Write-Log "脚本已在管理员模式下成功运行。"

# --- 配置 ---
$Host.UI.RawUI.WindowTitle = "IconForge Pro - 安装与启动"
$venvName = "myenv"
$pythonScriptName = "IconForge.py"
$venvDir = Join-Path $scriptDir $venvName
Write-Log "配置加载完毕: venv=$venvName, script=$pythonScriptName"

# ============================================================================
# 环境检查与自动安装
# ============================================================================
Clear-Host
Write-Log "========================================="
Write-Log "  环境自检与部署"
Write-Log "========================================="

$pythonExePath = Join-Path $venvDir "Scripts" "python.exe"
$pipExePath = Join-Path $venvDir "Scripts" "pip.exe"
$activateScriptPath = Join-Path $venvDir "Scripts" "Activate.ps1"

$isVenvValid = $false
if ((Test-Path $pythonExePath) -and (Test-Path $pipExePath) -and (Test-Path $activateScriptPath)) {
    $isVenvValid = $true
}

if ($isVenvValid) {
    Write-Log "虚拟环境 '$venvName' 经过验证，完整有效。跳过安装。"
} else {
    Write-Log "虚拟环境 '$venvName' 不存在或不完整，将执行强制重建！" -Level "WARN"
    if (Test-Path $venvDir) {
        Write-Log "检测到不完整的 '$venvName' 文件夹，正在强制删除..."
        Remove-Item -Recurse -Force $venvDir
        Write-Log "旧环境文件夹已删除。"
    }

    Write-Log "开始全自动安装流程..."
    
    Write-Log "步骤 1/3: 检查系统 Python..."
    $pythonCheck = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCheck) {
        Write-Log "未在系统中找到 'python' 命令！请确保 Python 已正确安装并添加到 PATH。" -Level "FATAL"
        Read-Host "按回车键退出"; exit
    }
    Write-Log "系统 Python 已找到: $($pythonCheck.Source)"

    Write-Log "步骤 2/3: 创建虚拟环境..."
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { 
        Write-Log "创建虚拟环境失败！退出代码: $LASTEXITCODE" -Level "FATAL"
        Read-Host "按回车键退出"; exit 
    }
    Write-Log "虚拟环境创建成功。"

    Write-Log "步骤 3/3: 安装依赖库到虚拟环境中..."
    # 注意：此处通过指定绝对路径 ($pythonExePath) 来安装，并未激活当前 PowerShell 会话
    & $pythonExePath -m pip install --upgrade pip
    Write-Log "Pip 升级完成，退出代码: $LASTEXITCODE"

    & $pythonExePath -m pip install Pillow PyQt5 rembg requests
    if ($LASTEXITCODE -ne 0) {
        Write-Log "依赖库安装失败！Pip 进程退出代码: $LASTEXITCODE" -Level "FATAL"
        Read-Host "按回车键退出"; exit
    }
    Write-Log "依赖库安装成功。"
    Write-Log "环境配置流程完毕！"
}

# ============================================================================
# 自动启动主程序
# ============================================================================
Write-Host ""
Write-Log "环境已就绪，准备自动启动主程序..."
Write-Host "环境已就绪，准备自动启动主程序..." -ForegroundColor Green
Start-Sleep -Seconds 1
Clear-Host

Write-Host "正在启动 IconForge Pro... (程序的输出信息将显示在此窗口)" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------"

# 关键步骤: 为了能直接使用 "python" 命令并让它指向虚拟环境,
# 我们必须先在【当前 PowerShell 会话】中激活这个环境。
# 安装依赖时只是向虚拟环境写入文件，并未激活它。
Write-Log "正在激活虚拟环境以用于程序启动..."
. $activateScriptPath
Write-Log "虚拟环境已在当前会话中激活。"

# 现在，因为环境已激活，下面的 "python" 命令会自动解析为 "myenv\Scripts\python.exe"
Write-Log "执行命令: python $pythonScriptName"
python $pythonScriptName


Write-Log "主程序已退出。脚本执行完毕。"
Write-Host "------------------------------------------------------------"
Write-Host "程序已退出。" -ForegroundColor White
Read-Host "按回车键关闭此窗口"

# 脚本结束
exit