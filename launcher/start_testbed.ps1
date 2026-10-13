# KIIS 테스트베드 원클릭 실행 — 시뮬레이션(Unity 트윈) + ROS 2 테스트베드 + 보드 vs 시뮬레이션 모니터 + 키보드 조종
# 컨트롤 패널(보드)은 플러그 앤 플레이: 이 창이 USB를 감시하다가 아두이노가 꽂히면 WSL에 붙이고,
# WSL의 패널 브리지가 자동으로 연결한다. 보드가 없으면 시뮬레이션만 돈다.
#   start_testbed.bat                       (더블클릭)
#   .\start_testbed.ps1 -Record             (~/kiis_logs/runs/<시각>/log.csv 기록)
#   .\start_testbed.ps1 -NoTeleop -NoUnity  (조종 탭 없이 / Unity는 이미 Play 중)
# 펌웨어를 올릴 때(Arduino IDE)는 이 창을 닫고 `usbipd detach --busid <ID>`로 보드를 윈도우에 돌려줄 것.
param(
    [switch]$Record,
    [switch]$NoTeleop,
    [switch]$NoUnity,
    [string]$Distro = 'Ubuntu',
    [int]$WatchSeconds = 0          # 0 = USB 감시를 Ctrl+C까지 계속 (점검용으로 초 단위 제한 가능)
)
$ErrorActionPreference = 'Stop'
$Root    = Split-Path -Parent $PSScriptRoot                       # 저장소 루트
$Project = Join-Path $Root 'unity\auto_car'
# Unity 에디터: 프로젝트가 요구하는 버전(ProjectVersion.txt)을 Hub 설치 위치들에서 찾는다
$UnityVer = ((Get-Content (Join-Path $Project 'ProjectSettings\ProjectVersion.txt')) -match '^m_EditorVersion:')[0].Split(':')[1].Trim()
$hubDirs = @("$env:ProgramFiles\Unity\Hub\Editor", 'D:\Unity\Editors', 'C:\Unity\Editors')
$sec = Join-Path $env:APPDATA 'UnityHub\secondaryInstallPath.json'
if (Test-Path $sec) { try { $p = Get-Content $sec -Raw | ConvertFrom-Json; if ($p) { $hubDirs = @($p) + $hubDirs } } catch {} }
$UnityExe = $hubDirs | ForEach-Object { Join-Path $_ "$UnityVer\Editor\Unity.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $UnityExe) { $UnityExe = "(Unity $UnityVer 미설치 — Unity Hub에서 설치)" }
$WslDir  = '/mnt/' + $Root.Substring(0,1).ToLower() + $Root.Substring(2).Replace('\', '/') + '/launcher'
$PanelVids = @('2341','2a03','1a86','0403')                      # Arduino 정품·Arduino.org·CH340·FTDI (CP210x=라이다는 제외)

# 모니터 = WSL의 web_monitor_node가 여는 http://localhost:8765 (WSLg 창은 안 그려지거나 뒤에 숨는 문제가 있어 브라우저로, 10-12)
$MonitorUrl = 'http://127.0.0.1:8765'   # localhost는 IPv6(::1)부터 시도해 1초를 넘기므로 IPv4로 고정
Add-Type -Namespace Kiis -Name Win -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c);
[DllImport("user32.dll")] public static extern bool SetWindowPos(System.IntPtr h, System.IntPtr after, int x, int y, int cx, int cy, uint f);
'@
# 윈도우는 백그라운드 프로세스의 포커스 가져오기를 막는다 → 잠깐 "항상 위"로 올렸다 해제해서 맨 앞에 놓는다
function Raise-Window($hwnd) {
    [void][Kiis.Win]::ShowWindow($hwnd, 9)
    [void][Kiis.Win]::SetWindowPos($hwnd, [IntPtr](-1), 0, 0, 0, 0, 0x43)
    Start-Sleep -Milliseconds 300
    [void][Kiis.Win]::SetWindowPos($hwnd, [IntPtr](-2), 0, 0, 0, 0, 0x43)
}
function Find-MonitorWindow {
    Get-Process chrome, msedge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'KIIS 테스트베드 모니터*' } | Select-Object -First 1
}
function Open-Monitor {
    try { $null = Invoke-WebRequest -Uri "$MonitorUrl/state" -UseBasicParsing -TimeoutSec 2 } catch { return $false }
    $w = Find-MonitorWindow
    if ($w) { Raise-Window $w.MainWindowHandle; return $true }   # 이미 열려 있으면 새로 열지 않고 앞으로
    # 기존 브라우저 창의 뒤쪽 탭으로 열리면 안 보이므로, 주소창 없는 독립 앱 창(--app)으로 연다 (Chrome → Edge → 기본 브라우저)
    $exe = $null
    foreach ($name in 'chrome.exe', 'msedge.exe') {
        foreach ($hive in 'HKCU:', 'HKLM:') {
            $k = Get-ItemProperty "$hive\Software\Microsoft\Windows\CurrentVersion\App Paths\$name" -ErrorAction SilentlyContinue
            if ($k -and $k.'(default)' -and (Test-Path $k.'(default)')) { $exe = $k.'(default)'; break }
        }
        if ($exe) { break }
    }
    if ($exe) { Start-Process $exe -ArgumentList "--app=$MonitorUrl", '--new-window', '--window-size=1250,860' }
    else { Start-Process $MonitorUrl }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 300
        $w = Find-MonitorWindow
        if ($w) { Raise-Window $w.MainWindowHandle; break }
    }
    return $true
}
function Say($msg, $color = 'Gray') { Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $msg) -ForegroundColor $color }

# ---- 1. 시뮬레이션 (Unity 디지털 트윈) ----
function Test-TwinListening { [bool](Get-NetTCPConnection -LocalPort 55002 -State Listen -ErrorAction SilentlyContinue) }
if (-not $NoUnity) {
    $editor = Get-CimInstance Win32_Process -Filter "Name='Unity.exe'" |
        Where-Object { $_.ExecutablePath -like '*\Editor\Unity.exe' -and $_.CommandLine -like "*$Project*" }
    if (Test-TwinListening) {
        Say '시뮬레이션: 이미 Play 중 (TCP 55002)' 'Green'
    } elseif ($editor) {
        New-Item -ItemType File -Force -Path (Join-Path $Project 'Temp\kiis_play.request') | Out-Null
        Say '시뮬레이션: 열린 Unity 에디터에 Play 요청을 보냄' 'Cyan'
    } elseif (Test-Path $UnityExe) {
        Start-Process -FilePath $UnityExe -ArgumentList @('-projectPath', "`"$Project`"", '-kiisAutoPlay')
        Say '시뮬레이션: Unity 에디터 실행 → 로딩이 끝나면 자동으로 Play (1~2분, Hub 로그인 필요)' 'Cyan'
    } else {
        Say "Unity 에디터를 찾을 수 없음: $UnityExe — Unity Hub에서 auto_car를 열고 Play를 직접 누를 것" 'Yellow'
    }
}

# ---- 2. ROS 2 테스트베드 + 모니터 창 + 조종 (WSL, Windows Terminal 탭) ----
$rec = if ($Record) { 'true' } else { 'false' }
$cal = Get-Content (Join-Path $Root 'twin\calibration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$extra = ''
if ($cal.panel.measured) { $extra = "panel_adc_left:=$($cal.panel.pot_left_adc) panel_adc_right:=$($cal.panel.pot_right_adc)" }
else { Say '패널 캘리브레이션이 아직 실측이 아님(twin/calibration.json measured=false) → 모니터에 패널은 ADC만 표시' 'Yellow' }
$tb = "wsl.exe -d $Distro -- bash $WslDir/wsl_testbed.sh $rec $extra"
# 이미 떠 있으면 두 벌이 되지 않게 (두 번째 트윈 브리지는 Unity에 못 붙고 상태 -1을 섞어 보낸다)
& wsl.exe -d $Distro -- pgrep -f "ros2 launch kiis_testbed" *> $null
$alreadyRunning = ($LASTEXITCODE -eq 0)
$tp = "wsl.exe -d $Distro -- bash $WslDir/wsl_teleop.sh"
if ($alreadyRunning) {
    Say 'ROS 2 테스트베드가 이미 실행 중 — 새로 띄우지 않음 (다시 띄우려면 "KIIS testbed" 탭에서 Ctrl+C 후 실행)' 'Yellow'
} elseif (Get-Command wt.exe -ErrorAction SilentlyContinue) {
    $wtArgs = "-w kiis new-tab --title `"KIIS testbed`" $tb"
    if (-not $NoTeleop) { $wtArgs += " ; new-tab --title `"KIIS teleop (g 주행허용, w/x 속도, a/d 조향, s 정지)`" $tp" }
    Start-Process wt.exe -ArgumentList $wtArgs
} else {
    Start-Process wsl.exe -ArgumentList "-d $Distro -- bash $WslDir/wsl_testbed.sh $rec $extra"
    if (-not $NoTeleop) { Start-Process wsl.exe -ArgumentList "-d $Distro -- bash $WslDir/wsl_teleop.sh" }
}
if (-not $alreadyRunning) { Say "ROS 2 테스트베드 · 조종 탭 실행 — 모니터는 준비되면 브라우저로 열림 ($MonitorUrl)" 'Green' }

# ---- 3. 컨트롤 패널 USB 감시 (플러그 앤 플레이) ----
if (-not (Get-Command usbipd -ErrorAction SilentlyContinue)) {
    Say 'usbipd가 없어 보드를 WSL에 붙일 수 없음 — 시뮬레이션만 사용 (winget install usbipd)' 'Yellow'
    return
}
Say '컨트롤 패널 대기 중 — 보드를 꽂으면 자동으로 연결합니다 (이 창을 닫으면 감시 종료, Ctrl+C)' 'Cyan'
$monitorShown = $false
$askedBind = @{}
$lastState = @{}
$t0 = Get-Date
while ($WatchSeconds -le 0 -or ((Get-Date) - $t0).TotalSeconds -lt $WatchSeconds) {
    if (-not $monitorShown -and (Open-Monitor)) { $monitorShown = $true; Say "모니터를 브라우저로 열었음: $MonitorUrl (탭을 닫아도 이 주소로 다시 열면 됨)" 'Green' }
    $seen = @{}
    $connected = $true
    foreach ($line in (usbipd list 2>$null)) {
        if ($line -match '^Persisted') { $connected = $false }
        if (-not $connected) { continue }
        if ($line -notmatch '^\s*(\d+-\d+)\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s+(.+?)\s{2,}(Not shared|Shared|Attached)\s*$') { continue }
        $busid, $vid, $desc, $state = $Matches[1], $Matches[2].ToLower(), $Matches[4].Trim(), $Matches[5]
        if (($PanelVids -notcontains $vid) -and ($desc -notmatch 'Arduino|CH340')) { continue }
        $seen[$busid] = $true
        if ($lastState[$busid] -ne $state) { Say "보드 감지: $busid $vid $desc — $state" 'Cyan'; $lastState[$busid] = $state }
        if ($state -eq 'Not shared' -and -not $askedBind[$busid]) {
            $askedBind[$busid] = $true
            Say "처음 보는 보드 → WSL 공유 등록(관리자 승인 창이 한 번 뜸): usbipd bind --busid $busid" 'Yellow'
            try { Start-Process usbipd -ArgumentList "bind --busid $busid" -Verb RunAs -Wait -WindowStyle Hidden } catch { Say "공유 등록 취소/실패: $_" 'Red' }
        } elseif ($state -eq 'Shared') {
            $out = usbipd attach --wsl --busid $busid 2>&1
            if ($LASTEXITCODE -eq 0) { Say "보드를 WSL에 연결: $busid → 패널 브리지가 곧 붙음 (모니터 왼쪽 카드 '연결됨')" 'Green' }
            else { Say "WSL 연결 실패: $out" 'Red' }
        }
    }
    foreach ($b in @($lastState.Keys)) { if (-not $seen[$b]) { Say "보드 분리됨: $b" 'Yellow'; $lastState.Remove($b) } }
    Start-Sleep -Seconds 2
}
