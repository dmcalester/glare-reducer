# Automatic Blind Control for Screen Glare Reduction

Automatically adjust window blinds based on sun position to reduce screen glare. Uses astronomical calculations to determine when sunlight will cause glare on your monitor, then triggers a macOS Shortcut to adjust your blinds accordingly.

## Features

- Precise sun position calculation based on your location
- Automatic terrain detection using GIS elevation data (hills, mountains)
- Configurable glare thresholds and response curves
- Integration with macOS Shortcuts for smart blind control
- Configuration stored in standard macOS plist format

## Requirements

- macOS with Shortcuts.app
- Python 3.9+ (included with macOS)
- Smart blinds controllable via HomeKit or other Shortcuts-compatible system

## How It Works

The system calculates the sun's position (azimuth and altitude) for your exact location and determines whether sunlight entering your window will cause glare on your monitor. It also accounts for terrain obstructions (hills, mountains) that may block the sun at low angles.

Based on the glare risk, it sends one of five levels to your Shortcut:

| Level | Meaning | Typical Blind Position |
|-------|---------|----------------------|
| `severe` | Maximum glare risk | Most closed (~35% open) |
| `high` | High glare risk | ~50% open |
| `moderate` | Moderate glare risk | ~70% open |
| `low` | Low glare risk | ~85% open |
| `none` | No glare risk | Fully open (100%) |

## Setup

### Step 1: Initialize Configuration

```bash
# Create the config file with defaults
python3 sun_position.py config-init
```

This creates `~/Library/Preferences/com.blinds.plist` with default settings.

### Step 2: Configure Your Location

Edit the config file:

```bash
open -a "Property List Editor" ~/Library/Preferences/com.blinds.plist
```

Or edit with any text editor (it's XML format). Key settings:

| Key | Description | Example |
|-----|-------------|---------|
| `latitude` | Your latitude (positive = North) | `40.7128` |
| `longitude` | Your longitude (negative = West) | `-74.0060` |
| `elevation` | Feet above sea level | `100` |
| `timezone` | Your timezone | `America/New_York` |
| `window_azimuth` | Direction window faces (0=N, 90=E, 180=S, 270=W) | `180` |
| `monitor_facing` | Direction your monitor faces | `270` |
| `user_facing` | Direction you face when working | `90` |

**Finding your coordinates:** Use https://www.latlong.net/ or any maps app.

**Finding your window azimuth:** Use a compass app on your phone while facing out the window.

### Step 3: Calculate Terrain Profile (Optional but Recommended)

If you have hills or mountains that block the sun at low angles:

```bash
python3 sun_position.py horizon
```

This queries elevation data from the Open-Elevation API and calculates when the sun will clear terrain obstructions in each direction. The profile is saved to `horizon_profile.json` and used automatically.

### Step 4: Create the macOS Shortcut

1. Open **Shortcuts.app**
2. Create a new Shortcut named exactly: `Reduce Glare`
3. The Shortcut should accept **text input** (the glare level)
4. Add logic to control your blinds based on the input

Example Shortcut structure:
```
Receive Shortcut Input
If Shortcut Input contains "severe"
    Control [Your Blinds] → Set to 35%
Otherwise if Shortcut Input contains "high"
    Control [Your Blinds] → Set to 50%
Otherwise if Shortcut Input contains "moderate"
    Control [Your Blinds] → Set to 70%
Otherwise if Shortcut Input contains "low"
    Control [Your Blinds] → Set to 85%
Otherwise
    Control [Your Blinds] → Set to 100%
End If
```

### Step 5: Test the Setup

```bash
# See current sun position and glare analysis
python3 sun_position.py

# Test what the automation would do (without running the Shortcut)
python3 sun_position.py auto-dry

# Run the automation for real
python3 sun_position.py auto
```

### Step 6: Set Up Automatic Scheduling

The included `com.blinds.plist` (in the project directory) is a macOS LaunchAgent that runs the script every 5 minutes during morning hours (6:30 AM - 10:00 AM).

1. Edit `com.blinds.plist` and update the paths:
   ```xml
   <string>/path/to/sun_position.py</string>
   ...
   <string>/path/to/blinds.log</string>
   ```

2. Copy to LaunchAgents folder:
   ```bash
   cp com.blinds.plist ~/Library/LaunchAgents/com.blinds.launchagent.plist
   ```

3. Load the agent:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.blinds.launchagent.plist
   ```

4. To stop automation:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.blinds.launchagent.plist
   ```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python3 sun_position.py` | Full interactive analysis with timeline |
| `python3 sun_position.py auto` | Run automation (executes Shortcut) |
| `python3 sun_position.py auto-dry` | Show what would run without executing |
| `python3 sun_position.py status` | One-line status summary |
| `python3 sun_position.py json` | Output all data as JSON |
| `python3 sun_position.py step` | Output just the step name |
| `python3 sun_position.py risk` | Output just the glare risk percentage |
| `python3 sun_position.py config` | Show current configuration |
| `python3 sun_position.py config-init` | Create config file with defaults |
| `python3 sun_position.py horizon` | Calculate terrain profile from GIS data |
| `python3 sun_position.py horizon-show` | Display saved terrain profile |
| `python3 sun_position.py help` | Show help |

## Configuration

All settings are stored in `~/Library/Preferences/com.blinds.plist`.

### Glare Response Settings

| Key | Default | Description |
|-----|---------|-------------|
| `day_blind_min_open` | `10` | Minimum open % (never fully closed) |
| `day_blind_max_open` | `100` | Maximum open % (fully retracted) |
| `glare_threshold_low` | `20` | Below this: blinds stay fully open |
| `glare_threshold_high` | `100` | At this level: blinds at minimum |
| `glare_response_curve` | `1.0` | 1.0=linear, <1=gentler, >1=aggressive |

### Manual Terrain Obstructions

If the GIS data doesn't capture a specific obstruction (like a nearby building), you can add manual entries to `horizon_obstructions` in the plist:

```xml
<key>horizon_obstructions</key>
<array>
    <dict>
        <key>azimuth_start</key>
        <integer>100</integer>
        <key>azimuth_end</key>
        <integer>130</integer>
        <key>min_altitude</key>
        <integer>8</integer>
    </dict>
</array>
```

This would block glare calculations when the sun is between 100°-130° azimuth and below 8° altitude.

## How Glare is Calculated

The glare model uses two primary factors:

1. **Sun Altitude (50% weight):** Low sun (< 25°) creates the most glare as it streams in at eye/screen level. Below 10° is considered maximum risk.

2. **Entry Angle (50% weight):** How directly sunlight enters through the window. Sun perpendicular to the window (0° entry angle) creates maximum glare; sun at wide angles (>60°) creates minimal direct glare.

When both factors align (low sun + direct entry), a 1.3x multiplier is applied.

Before calculating glare, the system checks:
- Is the sun above the horizon?
- Is the sun blocked by terrain (from GIS data or manual obstructions)?
- Can the sun enter the window based on its field of view?

## Files

| File | Purpose |
|------|---------|
| `sun_position.py` | Main script |
| `~/Library/Preferences/com.blinds.plist` | Configuration (created by config-init) |
| `horizon_profile.json` | Cached GIS terrain data (created by horizon command) |
| `com.blinds.plist` | LaunchAgent template for scheduling |

## Troubleshooting

**Shortcut not found:**
- Ensure the Shortcut is named exactly `Reduce Glare`
- Test running it manually: `shortcuts run "Reduce Glare" <<< "moderate"`

**Wrong glare timing:**
- Run `python3 sun_position.py horizon` to detect terrain
- Check if your elevation is correct (the horizon command will query it)
- Add manual obstructions if needed for buildings/trees

**Wrong glare calculations:**
- Verify your latitude/longitude are correct
- Check your window azimuth with a compass
- Run `python3 sun_position.py` to see detailed analysis

**LaunchAgent not running:**
- Check the log file for errors
- Verify paths in the plist are absolute paths
- Ensure Python 3.9+ is at `/usr/bin/python3`

## License

MIT License - Feel free to use and modify.
