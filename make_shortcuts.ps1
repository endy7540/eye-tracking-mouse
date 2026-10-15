# 프로젝트 폴더 안에 예쁜 이름·아이콘의 바로가기를 만든다 (.lnk는 .gitignore로 깃허브에 안 올라감)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outdir = $root   # 바로가기를 만들 곳 (바탕화면에 만들려면 [Environment]::GetFolderPath('Desktop') 로 바꾸기)
$ws = New-Object -ComObject WScript.Shell

function New-Shortcut($name, $bat, $icon, $desc) {
    $target = Join-Path $root $bat
    if (-not (Test-Path $target)) { Write-Host "건너뜀: $bat 파일이 없어요"; return }
    $lnk = $ws.CreateShortcut((Join-Path $outdir ($name + ".lnk")))
    $lnk.TargetPath = $target
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = (Join-Path $root $icon) + ",0"
    $lnk.WindowStyle = 7
    $lnk.Description = $desc
    $lnk.Save()
    Write-Host "만들었어요: $name"
}

New-Shortcut "눈동자 마우스" "start.bat" "ui\assets\app.ico" "눈으로 움직이는 마우스 시작"
New-Shortcut "눈동자 마우스 (다시 맞추기)" "recalibrate.bat" "ui\assets\app.ico" "캘리브레이션을 다시 하고 시작"
New-Shortcut "미니게임" "minigames.bat" "ui\assets\game.ico" "시선으로 하는 미니게임 모음"
