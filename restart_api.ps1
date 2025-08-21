# 重启搜索API脚本
Write-Host "Stopping existing API processes..."

# 查找并停止占用8000端口的进程
$processes = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($processes) {
    foreach ($proc in $processes) {
        $processId = $proc.OwningProcess
        Write-Host "Stopping process PID: $processId"
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

# 等待一下确保进程完全停止
Start-Sleep -Seconds 2

Write-Host "Starting new API instance..."
# 启动新的API实例
cd "c:\Users\sunying\Desktop\graphRAG\search_api"
conda activate sapi
python app.py
