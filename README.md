# Splash Reminders

A Windows system tray application that reminds you to take breaks, stay hydrated, and stretch.

## Features

- **Full-screen splash reminders** with dark theme
- **System tray icon** for easy control
- **Pause mode** - shows mini popups instead (for meetings/presentations)
- **Interval reminders** - every X minutes (e.g., drink water every 20 min)
- **Scheduled reminders** - at specific times (e.g., lunch at 12:00)
- **Auto-start** with Windows

## Requirements

- Python 3.10+
- Windows 10/11

## Installation

1. Clone this repository
2. Install dependencies:
   ```
   pip install pystray pillow
   ```
3. Run:
   ```
   python reminder_service.py
   ```

## Auto-Start on Windows

### Option 1: Run the install script

Save this as `install_startup.bat` in the project folder and run it:

```batch
@echo off
set "SCRIPT_DIR=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP%\SplashReminders.lnk'); $s.TargetPath = 'pythonw.exe'; $s.Arguments = '%SCRIPT_DIR%reminder_service.py'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"

echo Installed to startup. Splash Reminders will run on login.
pause
```

### Option 2: Manual setup

1. Press `Win + R`, type `shell:startup`, press Enter
2. Create a shortcut with:
   - Target: `pythonw.exe D:\path\to\reminder_service.py`
   - Start in: `D:\path\to\`

### Uninstall from startup

Delete `SplashReminders.lnk` from `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`

## Configuration

Edit `config.json` to customize your reminders:

```json
{
    "reminders": [
        {
            "message": "Stand Up & Stretch!",
            "interval_minutes": 30,
            "color": "#FF6B35"
        },
        {
            "message": "Drink Water - Stay Hydrated!",
            "interval_minutes": 20,
            "color": "#4ECDC4"
        }
    ],
    "scheduled": [
        {
            "message": "Lunch Time!",
            "time": "12:00:00",
            "color": "#E74C3C"
        }
    ],
    "display_seconds": 8,
    "font_size": 72,
    "play_sound": true
}
```

### Options

| Option | Description |
|--------|-------------|
| `reminders` | Interval-based reminders (every X minutes/seconds) |
| `scheduled` | Time-based reminders (at specific times daily) |
| `display_seconds` | How long the splash stays on screen |
| `font_size` | Size of the reminder text |
| `play_sound` | Play a sound when reminder appears |

### Interval Options

`interval_minutes` supports decimals for sub-minute intervals:

```json
{"message": "Every 30 minutes", "interval_minutes": 30, "color": "#FF6B35"}
{"message": "Every 18 seconds", "interval_minutes": 0.3, "color": "#4ECDC4"}
{"message": "Every 36 seconds", "interval_minutes": 0.6, "color": "#9B59B6"}
```

### Time Format

- `"HH:MM:SS"` - e.g., `"13:30:00"` for 1:30 PM
- `"HH:MM"` - e.g., `"09:00"` for 9:00 AM

## Tray Menu

Right-click the tray icon to access:

- **Start/Stop Reminders** - Toggle reminders on/off
- **Pause (Mini Popups)** - Switch to small corner popups
- **Resume (Full Splash)** - Back to full-screen reminders
- **Edit Schedule** - Open config.json in your editor
- **Reload Config** - Apply changes without restarting
- **Quit** - Exit the application

## License

MIT
