# VANOVA Update Progress Window (WinForms, ASCII-only)
# Failures here must never block the external updater.
$script:UpdateProgressAvailable = $false
$script:UpdateProgressForm = $null
$script:UpdateProgressLabels = @()
$script:UpdateProgressBar = $null
$script:UpdateProgressDetail = $null

$script:UpdateSteps = @(
    "Preparando",
    "Cerrando VANOVA",
    "Instalando actualizacion",
    "Reiniciando VANOVA"
)

try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop
    $script:UpdateProgressAvailable = $true
} catch {
    $script:UpdateProgressAvailable = $false
}

function Start-UpdateProgressWindow {
    param(
        [string]$Version = ""
    )

    if (-not $script:UpdateProgressAvailable) { return }
    if ($script:UpdateProgressForm) { return }

    try {
        $form = New-Object System.Windows.Forms.Form
        $form.Text = "Actualizando VANOVA"
        $form.Size = New-Object System.Drawing.Size(440, 280)
        $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
        $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
        $form.MaximizeBox = $false
        # La ventana debe poder minimizarse (no bloquear al usuario durante la
        # actualización) y no flotar siempre por encima de las demás ventanas.
        $form.MinimizeBox = $true
        $form.TopMost = $false
        $form.ShowInTaskbar = $true
        $form.BackColor = [System.Drawing.Color]::FromArgb(28, 28, 32)
        $form.ForeColor = [System.Drawing.Color]::White

        $title = New-Object System.Windows.Forms.Label
        $title.Text = "Actualizando VANOVA"
        $title.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
        $title.ForeColor = [System.Drawing.Color]::White
        $title.AutoSize = $true
        $title.Location = New-Object System.Drawing.Point(24, 20)
        $form.Controls.Add($title)

        $verText = if ($Version) { "Version " + $Version } else { "Instalando actualizacion..." }
        $verLbl = New-Object System.Windows.Forms.Label
        $verLbl.Text = $verText
        $verLbl.Font = New-Object System.Drawing.Font("Segoe UI", 9)
        $verLbl.ForeColor = [System.Drawing.Color]::FromArgb(180, 180, 190)
        $verLbl.AutoSize = $true
        $verLbl.Location = New-Object System.Drawing.Point(26, 52)
        $form.Controls.Add($verLbl)

        $labels = @()
        $y = 88
        foreach ($step in $script:UpdateSteps) {
            $lbl = New-Object System.Windows.Forms.Label
            $lbl.Text = "  " + $step
            $lbl.Font = New-Object System.Drawing.Font("Segoe UI", 10)
            $lbl.ForeColor = [System.Drawing.Color]::FromArgb(120, 120, 130)
            $lbl.AutoSize = $true
            $lbl.Location = New-Object System.Drawing.Point(24, $y)
            $form.Controls.Add($lbl)
            $labels += $lbl
            $y += 26
        }

        $detail = New-Object System.Windows.Forms.Label
        $detail.Text = "Por favor espera..."
        $detail.Font = New-Object System.Drawing.Font("Segoe UI", 8)
        $detail.ForeColor = [System.Drawing.Color]::FromArgb(140, 140, 150)
        $detail.AutoSize = $true
        $detail.Location = New-Object System.Drawing.Point(26, 198)
        $form.Controls.Add($detail)

        $bar = New-Object System.Windows.Forms.ProgressBar
        $bar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
        $bar.MarqueeAnimationSpeed = 25
        $bar.Size = New-Object System.Drawing.Size(380, 8)
        $bar.Location = New-Object System.Drawing.Point(24, 222)
        $form.Controls.Add($bar)

        $script:UpdateProgressForm = $form
        $script:UpdateProgressLabels = $labels
        $script:UpdateProgressBar = $bar
        $script:UpdateProgressDetail = $detail

        $form.Add_Shown({ $form.Activate() })
        $form.Show()
        [System.Windows.Forms.Application]::DoEvents()
    } catch {
        $script:UpdateProgressAvailable = $false
        $script:UpdateProgressForm = $null
        throw
    }
}

function Set-UpdateProgressStep {
    param(
        [int]$StepIndex = 0,
        [string]$Detail = ""
    )

    if (-not $script:UpdateProgressAvailable -or -not $script:UpdateProgressForm) { return }

    try {
        for ($i = 0; $i -lt $script:UpdateProgressLabels.Count; $i++) {
            $lbl = $script:UpdateProgressLabels[$i]
            if ($i -lt $StepIndex) {
                $lbl.Text = "[OK] " + $script:UpdateSteps[$i]
                $lbl.ForeColor = [System.Drawing.Color]::FromArgb(80, 180, 100)
            } elseif ($i -eq $StepIndex) {
                $lbl.Text = ">> " + $script:UpdateSteps[$i]
                $lbl.ForeColor = [System.Drawing.Color]::FromArgb(220, 140, 100)
            } else {
                $lbl.Text = "   " + $script:UpdateSteps[$i]
                $lbl.ForeColor = [System.Drawing.Color]::FromArgb(120, 120, 130)
            }
        }

        if ($Detail -and $script:UpdateProgressDetail) {
            $script:UpdateProgressDetail.Text = $Detail
        }

        [System.Windows.Forms.Application]::DoEvents()
    } catch { }
}

function Close-UpdateProgressWindow {
    if (-not $script:UpdateProgressForm) { return }
    try {
        $script:UpdateProgressForm.Close()
        $script:UpdateProgressForm.Dispose()
    } catch { }
    $script:UpdateProgressForm = $null
    $script:UpdateProgressLabels = @()
    $script:UpdateProgressBar = $null
    $script:UpdateProgressDetail = $null
}
