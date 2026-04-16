param(
    [string]$Command = "start",
    [switch]$Follow,
    [int]$Tail = 80,
    [switch]$Force,
    [switch]$Fix
)

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv"
$FrontendDir = Join-Path $ProjectDir "frontend"
$LogDir = Join-Path $ProjectDir "logs"
$PidDir = Join-Path $ProjectDir ".pids"
$EnvFile = Join-Path $ProjectDir ".env"
$EnvExampleFile = Join-Path $ProjectDir ".env.example"

$BackendPidFile = Join-Path $PidDir "backend.pid"
$FrontendPidFile = Join-Path $PidDir "frontend.pid"
$BackendLogFile = Join-Path $LogDir "backend.log"
$FrontendLogFile = Join-Path $LogDir "frontend.log"

$BackendPort = if ($env:NEXUS_BACKEND_PORT) { [int]$env:NEXUS_BACKEND_PORT } else { 43817 }
$FrontendPort = if ($env:NEXUS_FRONTEND_PORT) { [int]$env:NEXUS_FRONTEND_PORT } else { 43819 }
$DockerContainerName = "nexus-postgres"
$script:BootstrapChangedEnv = $false
$script:PythonLauncherFile = $null
$script:PythonLauncherArgs = @()
$script:NodeFile = $null
$script:NpmFile = $null

function Write-Ok([string]$Message) {
    Write-Host " [OK] $Message" -ForegroundColor Green
}

function Write-WarnMsg([string]$Message) {
    Write-Host " [WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail([string]$Message) {
    Write-Host " [FAIL] $Message" -ForegroundColor Red
}

function Write-Note([string]$Message) {
    Write-Host " $Message" -ForegroundColor DarkGray
}

function Write-Banner {
    Write-Host ""
    Write-Host " Nexus Windows Runner" -ForegroundColor Cyan
    Write-Host ("-" * 64) -ForegroundColor DarkGray
    Write-Host (" API      http://localhost:{0}" -f $BackendPort)
    Write-Host (" Docs     http://localhost:{0}/docs" -f $BackendPort)
    Write-Host (" Swagger  http://localhost:{0}/swagger" -f $BackendPort)
    Write-Host (" Frontend http://localhost:{0}" -f $FrontendPort)
    Write-Host (" Logs     {0}" -f $LogDir)
    Write-Host ("-" * 64) -ForegroundColor DarkGray
}

function Ensure-Directories {
    foreach ($dir in @($LogDir, $PidDir)) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir | Out-Null
        }
    }
}

function Get-EnvMap {
    $map = @{}
    if (-not (Test-Path $EnvFile)) {
        return $map
    }

    foreach ($line in Get-Content -Path $EnvFile -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith("#")) {
            continue
        }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) {
            continue
        }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1)
        $map[$key] = $value
    }
    return $map
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = @()
    if (Test-Path $EnvFile) {
        $lines = Get-Content -Path $EnvFile -Encoding UTF8
    }

    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Key))=") {
            $lines[$i] = "$Key=$Value"
            $updated = $true
            break
        }
    }

    if (-not $updated) {
        $lines += "$Key=$Value"
    }

    Set-Content -Path $EnvFile -Value $lines -Encoding UTF8
    $script:BootstrapChangedEnv = $true
}

function Ensure-EnvFile {
    if (-not (Test-Path $EnvFile)) {
        if (-not (Test-Path $EnvExampleFile)) {
            throw "Missing .env.example at $EnvExampleFile"
        }
        Copy-Item $EnvExampleFile $EnvFile
        Write-Ok "Created .env from .env.example"
    }

    $envMap = Get-EnvMap
    $defaults = @{
        "DB_BACKEND" = "postgres"
        "POSTGRES_HOST" = "127.0.0.1"
        "POSTGRES_PORT" = "5432"
        "POSTGRES_USER" = "postgres"
        "POSTGRES_PASSWORD" = "nexus_dev_password"
        "POSTGRES_DB" = "nexus"
    }

    foreach ($key in $defaults.Keys) {
        $value = if ($envMap.ContainsKey($key)) { $envMap[$key] } else { "" }
        if ([string]::IsNullOrWhiteSpace($value)) {
            Set-EnvValue -Key $key -Value $defaults[$key]
            Write-Note "Updated .env: $key=$($defaults[$key])"
        }
    }

    if ($script:BootstrapChangedEnv) {
        Write-Ok ".env normalized for local bootstrap"
    }
}

function Resolve-PythonLauncher {
    if ($script:PythonLauncherFile) {
        return
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $version = & $py.Source -3.11 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
            if ($LASTEXITCODE -eq 0 -and $version) {
                $script:PythonLauncherFile = $py.Source
                $script:PythonLauncherArgs = @("-3.11")
                return
            }
        } catch {
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python 3.11+ is required. Install Python 3.11 and ensure 'py' or 'python' is on PATH."
    }

    $version = & $python.Source -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to execute Python from PATH."
    }
    $parts = $version.Trim().Split(".")
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
        throw "Python 3.11+ is required. Current version: $version"
    }

    $script:PythonLauncherFile = $python.Source
    $script:PythonLauncherArgs = @()
}

function Invoke-PythonLauncher {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )
    Resolve-PythonLauncher
    & $script:PythonLauncherFile @script:PythonLauncherArgs @Arguments
    return $LASTEXITCODE
}

function Get-VenvPython {
    $path = Join-Path $VenvDir "Scripts\\python.exe"
    if (-not (Test-Path $path)) {
        throw "Virtual environment python not found: $path"
    }
    return $path
}

function Get-VenvPip {
    $path = Join-Path $VenvDir "Scripts\\pip.exe"
    if (-not (Test-Path $path)) {
        throw "Virtual environment pip not found: $path"
    }
    return $path
}

function Ensure-NodeTools {
    if (-not $script:NodeFile) {
        $node = Get-Command node -ErrorAction SilentlyContinue
        if (-not $node) {
            throw "Node.js 20+ is required. Install Node.js and ensure 'node' is on PATH."
        }
        $nodeVersion = & $node.Source -p "process.versions.node"
        $major = [int]($nodeVersion.Trim().Split(".")[0])
        if ($major -lt 20) {
            throw "Node.js 20+ is required. Current version: $nodeVersion"
        }
        $script:NodeFile = $node.Source
    }

    if (-not $script:NpmFile) {
        $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npm) {
            $npm = Get-Command npm -ErrorAction SilentlyContinue
        }
        if (-not $npm) {
            throw "npm is required. Ensure npm is installed and on PATH."
        }
        $script:NpmFile = $npm.Source
    }
}

function Ensure-BackendEnv {
    Resolve-PythonLauncher
    if (-not (Test-Path $VenvDir)) {
        Write-Note "Creating Python virtual environment..."
        $exitCode = Invoke-PythonLauncher -m venv $VenvDir
        if ($exitCode -ne 0) {
            throw "Failed to create virtual environment"
        }
    }

    $venvPython = Get-VenvPython
    $importsOk = $false
    try {
        & $venvPython -c "import fastapi, uvicorn, asyncpg, playwright, multipart"
        $importsOk = ($LASTEXITCODE -eq 0)
    } catch {
        $importsOk = $false
    }

    if (-not $importsOk) {
        Write-Note "Installing backend dependencies..."
        & (Get-VenvPip) install --upgrade pip | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip in virtual environment" }
        & (Get-VenvPip) install -e ".[dev]" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to install backend dependencies" }
        & (Get-VenvPip) install python-multipart | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to install python-multipart" }
        Write-Ok "Backend dependencies installed"
    }
}

function Ensure-PlaywrightBrowser {
    $venvPython = Get-VenvPython
    $browserOk = $false
    try {
        & $venvPython -c "from playwright.sync_api import sync_playwright; pw = sync_playwright().start(); browser = pw.chromium.launch(headless=True); browser.close(); pw.stop()"
        $browserOk = ($LASTEXITCODE -eq 0)
    } catch {
        $browserOk = $false
    }

    if (-not $browserOk) {
        Write-Note "Installing Playwright Chromium..."
        & $venvPython -m playwright install chromium | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to install Playwright Chromium" }
        Write-Ok "Playwright Chromium installed"
    }
}

function Ensure-FrontendEnv {
    Ensure-NodeTools
    $nodeModules = Join-Path $FrontendDir "node_modules"
    if (-not (Test-Path $nodeModules)) {
        Write-Note "Installing frontend dependencies..."
        Push-Location $FrontendDir
        try {
            & $script:NpmFile ci | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Failed to install frontend dependencies" }
        } finally {
            Pop-Location
        }
        Write-Ok "Frontend dependencies installed"
    }
}

function Get-EnvOrDefault($Map, [string]$Key, [string]$DefaultValue) {
    if ($Map.ContainsKey($Key) -and -not [string]::IsNullOrWhiteSpace($Map[$Key])) {
        return $Map[$Key]
    }
    return $DefaultValue
}

function Get-ListeningPid([int]$Port) {
    try {
        $line = (netstat -ano -p tcp | Select-String -Pattern "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$" | Select-Object -First 1).Line
        if ($line) {
            $tokens = $line -split "\s+"
            $portOwnerPid = $tokens[-1]
            if ($portOwnerPid -match "^\d+$") {
                return [int]$portOwnerPid
            }
        }
    } catch {
    }
    return $null
}

function Test-PortListening([int]$Port) {
    return $null -ne (Get-ListeningPid -Port $Port)
}

function Read-Pid([string]$PidFile) {
    if (-not (Test-Path $PidFile)) {
        return $null
    }
    $raw = (Get-Content -Path $PidFile -Encoding UTF8 | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return [int]$raw
}

function Test-PidRunning([int]$Pid) {
    try {
        Get-Process -Id $Pid -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Stop-PidTree([int]$Pid, [string]$Name) {
    if (-not (Test-PidRunning -Pid $Pid)) {
        return
    }
    & taskkill.exe /PID $Pid /T /F | Out-Null
    Write-Ok "$Name stopped (PID $Pid)"
}

function Wait-ForPort([int]$Port, [int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening -Port $Port) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Ensure-DockerCommand {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        return $null
    }
    return $docker.Source
}

function Ensure-PostgresReady {
    $envMap = Get-EnvMap
    $backend = (Get-EnvOrDefault $envMap "DB_BACKEND" "postgres").ToLowerInvariant()
    if ($backend -eq "supabase") {
        $supabaseUrl = Get-EnvOrDefault $envMap "SUPABASE_URL" ""
        $supabaseKey = Get-EnvOrDefault $envMap "SUPABASE_KEY" ""
        if ([string]::IsNullOrWhiteSpace($supabaseUrl) -or [string]::IsNullOrWhiteSpace($supabaseKey)) {
            throw "DB_BACKEND=supabase but SUPABASE_URL or SUPABASE_KEY is missing in .env"
        }
        Write-Ok "Supabase backend configured"
        return
    }

    $host = Get-EnvOrDefault $envMap "POSTGRES_HOST" "127.0.0.1"
    $port = [int](Get-EnvOrDefault $envMap "POSTGRES_PORT" "5432")
    $user = Get-EnvOrDefault $envMap "POSTGRES_USER" "postgres"
    $password = Get-EnvOrDefault $envMap "POSTGRES_PASSWORD" "nexus_dev_password"
    $database = Get-EnvOrDefault $envMap "POSTGRES_DB" "nexus"
    $docker = Ensure-DockerCommand

    if (-not (Test-PortListening -Port $port)) {
        if ($host -notin @("127.0.0.1", "localhost")) {
            throw "PostgreSQL is not reachable at $host`:$port"
        }

        if (-not $docker) {
            throw "PostgreSQL is not running on $host`:$port and Docker was not found. Start PostgreSQL manually or install Docker Desktop."
        }

        Write-Note "PostgreSQL is not running; starting local Docker container..."
        $existingNames = & $docker ps -a --format "{{.Names}}"
        if ($existingNames -contains $DockerContainerName) {
            & $docker start $DockerContainerName | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Failed to start Docker container $DockerContainerName" }
        } else {
            & $docker run `
                --name $DockerContainerName `
                -e "POSTGRES_USER=$user" `
                -e "POSTGRES_PASSWORD=$password" `
                -e "POSTGRES_DB=postgres" `
                -p "${port}:5432" `
                -d postgres:16-alpine | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Failed to create Docker container $DockerContainerName" }
        }

        if (-not (Wait-ForPort -Port $port -TimeoutSeconds 90)) {
            throw "Timed out waiting for PostgreSQL on port $port"
        }
        Write-Ok "Local PostgreSQL container is ready"
    }

    $venvPython = Get-VenvPython
    $bootstrapOutput = & $venvPython scripts/bootstrap_db.py --env-file $EnvFile --json
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to bootstrap PostgreSQL schema"
    }
    $bootstrapResult = $bootstrapOutput | ConvertFrom-Json
    if (-not $bootstrapResult.ok) {
        throw "PostgreSQL bootstrap failed: $($bootstrapResult.error)"
    }
    $state = if ($bootstrapResult.database_created) { "created" } else { "ready" }
    Write-Ok "PostgreSQL schema $state for database '$database'"
}

function Initialize-Workspace {
    Ensure-Directories
    Ensure-EnvFile
    Ensure-BackendEnv
    Ensure-PlaywrightBrowser
    Ensure-FrontendEnv
    Ensure-PostgresReady
}

function Show-Doctor {
    Write-Banner
    Ensure-Directories
    Write-Note "Running environment diagnostics..."

    try {
        Resolve-PythonLauncher
        $version = & $script:PythonLauncherFile @script:PythonLauncherArgs -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
        Write-Ok "Python launcher OK ($version)"
    } catch {
        Write-Fail $_.Exception.Message
    }

    try {
        Ensure-NodeTools
        $nodeVersion = & $script:NodeFile -p "process.versions.node"
        Write-Ok "Node.js OK ($nodeVersion)"
    } catch {
        Write-Fail $_.Exception.Message
    }

    if (Test-Path (Join-Path $VenvDir "Scripts\\python.exe")) {
        Write-Ok "Virtual environment exists"
    } else {
        Write-WarnMsg "Virtual environment missing"
    }

    if (Test-Path (Join-Path $FrontendDir "node_modules")) {
        Write-Ok "frontend/node_modules exists"
    } else {
        Write-WarnMsg "frontend/node_modules missing"
    }

    if (Test-Path $EnvFile) {
        Write-Ok ".env exists"
    } else {
        Write-WarnMsg ".env missing"
    }

    $envMap = Get-EnvMap
    $backend = (Get-EnvOrDefault $envMap "DB_BACKEND" "postgres").ToLowerInvariant()
    if ($backend -eq "postgres") {
        $pgPort = [int](Get-EnvOrDefault $envMap "POSTGRES_PORT" "5432")
        if (Test-PortListening -Port $pgPort) {
            Write-Ok "PostgreSQL port $pgPort is listening"
        } else {
            Write-WarnMsg "PostgreSQL port $pgPort is not listening"
        }
    } else {
        Write-Ok "Supabase backend configured"
    }

    if ($Fix) {
        Write-Note "Applying automatic fixes..."
        Initialize-Workspace
    }
}

function Start-Backend {
    $pid = Read-Pid $BackendPidFile
    if ($pid -and (Test-PidRunning -Pid $pid)) {
        Write-Note "Backend already running (PID $pid), auto-restarting..."
        Stop-PidTree -Pid $pid -Name "Backend"
    }

    if (Test-Path $BackendPidFile) {
        Remove-Item $BackendPidFile -Force
    }

    $listener = Get-ListeningPid -Port $BackendPort
    if ($listener) {
        if ($pid -and $listener -eq $pid) {
            Write-Note "Backend port occupant matches previous PID $listener, already stopped."
        } else {
            Write-WarnMsg "Backend port $BackendPort is occupied by PID $listener, auto-stopping occupant."
            Stop-PidTree -Pid $listener -Name "Backend port occupant"
        }
    }

    $venvPython = Get-VenvPython
    $cmd = "`"$venvPython`" -m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort --reload >> `"$BackendLogFile`" 2>>&1"
    $process = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", $cmd) `
        -WorkingDirectory $ProjectDir `
        -PassThru
    Set-Content -Path $BackendPidFile -Value $process.Id -Encoding UTF8

    if (-not (Wait-ForPort -Port $BackendPort -TimeoutSeconds 60)) {
        throw "Backend failed to start. Check $BackendLogFile"
    }
    Write-Ok "Backend started (PID $($process.Id))"
}

function Start-Frontend {
    $pid = Read-Pid $FrontendPidFile
    if ($pid -and (Test-PidRunning -Pid $pid)) {
        Write-Note "Frontend already running (PID $pid), auto-restarting..."
        Stop-PidTree -Pid $pid -Name "Frontend"
    }

    if (Test-Path $FrontendPidFile) {
        Remove-Item $FrontendPidFile -Force
    }

    $listener = Get-ListeningPid -Port $FrontendPort
    if ($listener) {
        if ($pid -and $listener -eq $pid) {
            Write-Note "Frontend port occupant matches previous PID $listener, already stopped."
        } else {
            Write-WarnMsg "Frontend port $FrontendPort is occupied by PID $listener, auto-stopping occupant."
            Stop-PidTree -Pid $listener -Name "Frontend port occupant"
        }
    }

    Ensure-NodeTools
    $cmd = "set NEXT_PUBLIC_API_BASE_URL=http://localhost:$BackendPort/api/v1 && set PORT=$FrontendPort && `"$script:NpmFile`" run dev >> `"$FrontendLogFile`" 2>>&1"
    $process = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", $cmd) `
        -WorkingDirectory $FrontendDir `
        -PassThru
    Set-Content -Path $FrontendPidFile -Value $process.Id -Encoding UTF8

    if (-not (Wait-ForPort -Port $FrontendPort -TimeoutSeconds 90)) {
        throw "Frontend failed to start. Check $FrontendLogFile"
    }
    Write-Ok "Frontend started (PID $($process.Id))"
}

function Stop-ServiceFromPidFile([string]$PidFile, [string]$Name) {
    $pid = Read-Pid $PidFile
    if ($pid) {
        Stop-PidTree -Pid $pid -Name $Name
        if (Test-Path $PidFile) {
            Remove-Item $PidFile -Force
        }
        return
    }
    Write-Note "$Name is not tracked"
}

function Show-StatusLine([string]$Name, [string]$PidFile, [int]$Port, [string]$Url) {
    $pid = Read-Pid $PidFile
    if ($pid -and (Test-PidRunning -Pid $pid)) {
        Write-Host (" {0,-10} RUNNING  pid={1} port={2} {3}" -f $Name, $pid, $Port, $Url) -ForegroundColor Green
        return
    }

    $listener = Get-ListeningPid -Port $Port
    if ($listener) {
        Write-Host (" {0,-10} PORT-IN-USE pid={1} port={2} {3}" -f $Name, $listener, $Port, $Url) -ForegroundColor Yellow
        return
    }

    Write-Host (" {0,-10} STOPPED  pid=- port={1} {2}" -f $Name, $Port, $Url) -ForegroundColor Red
}

function Show-Status {
    Write-Banner
    Show-StatusLine -Name "backend" -PidFile $BackendPidFile -Port $BackendPort -Url "http://localhost:$BackendPort/docs"
    Show-StatusLine -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort -Url "http://localhost:$FrontendPort"
}

function Show-Logs([string]$Target) {
    $logFile = if ($Target -eq "frontend") { $FrontendLogFile } else { $BackendLogFile }
    if (-not (Test-Path $logFile)) {
        Write-WarnMsg "No log file at $logFile"
        return
    }
    if ($Follow) {
        Get-Content -Path $logFile -Tail $Tail -Wait
    } else {
        Get-Content -Path $logFile -Tail $Tail
    }
}

switch ($Command.ToLowerInvariant()) {
    "bootstrap" {
        Write-Banner
        Initialize-Workspace
        Show-Status
    }
    "doctor" {
        Show-Doctor
    }
    "start" {
        Write-Banner
        Initialize-Workspace
        Start-Backend
        Start-Frontend
        Show-Status
    }
    "stop" {
        Write-Banner
        Stop-ServiceFromPidFile -PidFile $FrontendPidFile -Name "Frontend"
        Stop-ServiceFromPidFile -PidFile $BackendPidFile -Name "Backend"
    }
    "restart" {
        Write-Banner
        Stop-ServiceFromPidFile -PidFile $FrontendPidFile -Name "Frontend"
        Stop-ServiceFromPidFile -PidFile $BackendPidFile -Name "Backend"
        Initialize-Workspace
        Start-Backend
        Start-Frontend
        Show-Status
    }
    "status" {
        Show-Status
    }
    "logs" {
        Show-Logs -Target "backend"
    }
    "logs-backend" {
        Show-Logs -Target "backend"
    }
    "logs-frontend" {
        Show-Logs -Target "frontend"
    }
    default {
        throw "Unsupported command '$Command'. Use bootstrap|doctor|start|stop|restart|status|logs|logs-backend|logs-frontend."
    }
}
