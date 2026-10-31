"""
Desktop notification helper for long-running NSFC download tasks.

Sends native OS notifications (Windows toast) and prints [PUSH] markers
that can be watched by Claude Code Monitor.
"""
import subprocess
import sys


def push(title, body):
    """Send a desktop notification. Prints marker + tries native OS toast.

    Returns True if native notification was attempted, False if only printed.
    """
    # Always print marker — Claude Code Monitor can watch for [PUSH]
    print(f"\n[PUSH] {title}: {body}\n")

    if sys.platform != "win32":
        return False

    # Escape single quotes in title and body for PowerShell
    safe_title = title.replace("'", "''")
    safe_body = body.replace("'", "''")

    ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
$balloon = New-Object System.Windows.Forms.NotifyIcon
$balloon.Icon = [System.Drawing.SystemIcons]::Information
$balloon.BalloonTipTitle = '{safe_title}'
$balloon.BalloonTipText = '{safe_body}'
$balloon.Visible = $true
$balloon.ShowBalloonTip(5000)
Start-Sleep -Seconds 6
$balloon.Dispose()
'''

    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True, timeout=10
        )
        return True
    except Exception:
        return False
