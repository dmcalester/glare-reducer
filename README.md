# Automatic Blind Control for Screen Glare Reduction

Automatically adjust window blinds based on sun position to reduce screen glare. Uses astronomical calculations to determine when sunlight will cause glare on your monitor, then triggers a macOS Shortcut to adjust your blinds accordingly.

## Requirements

- macOS with Shortcuts.app
- Python 3.9+ (included with macOS)
- Smart blinds controllable via HomeKit or other Shortcuts-compatible system

## How It Works

The system calculates the sun's position (azimuth and altitude) for your exact location and determines whether sunlight entering your window will cause glare on your monitor. Based on the glare risk, it sends one of five levels to your Shortcut:

| Level | Meaning | Typical Blind Position |
|-------|---------|----------------------|
| `severe` | Maximum glare risk | Most closed (~35% open) |
| `high` | High glare risk | ~50% open |
| `moderate` | Moderate glare risk | ~70% open |
| `low` | Low glare risk | ~85% open |
| `none` | No glare risk | Fully open (100%) |

## Setup

### Step 1: Configure Your Location

Edit `sun_position.py` and update the configuration section at the top:

```python
# Your location - REQUIRED
LATITUDE = 40.7128      # Your latitude (positive = North, negative = South)
LONGITUDE = -74.0060    # Your longitude (positive = East, negative = West)
TIMEZONE = "America/New_York"  # Your timezone

# Room configuration
WINDOW_AZIMUTH = 180    # Direction your window faces (0=N, 90=E, 180=S, 270=W)
MONITOR_FACING = 90     # Direction your monitor screen faces
USER_FACING = 270       # Direction you face when working
```

**Finding your coordinates:** Use https://www.latlong.net/ or any maps app.

**Finding your window azimuth:** Use a compass app on your phone while facing out the window.

### Step 2: Create the macOS Shortcut

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

### Step 3: Test the Setup

```bash
# See current sun position and glare analysis
python3 sun_position.py

# Test what the automation would do (without running the Shortcut)
python3 sun_position.py auto-dry

# Run the automation for real
python3 sun_position.py auto
```

### Step 4: Set Up Automatic Scheduling

The included `com.blinds.plist` is a macOS LaunchAgent that runs the script every 5 minutes during morning hours (6:30 AM - 10:00 AM).

1. Edit `com.blinds.plist` and update the paths:
   ```xml
   <string>/path/to/sun_position.py</string>
   ...
   <string>/path/to/blinds.log</string>
   ```

2. Copy to LaunchAgents folder:
   ```bash
   cp com.blinds.plist ~/Library/LaunchAgents/
   ```

3. Load the agent:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.blinds.plist
   ```

4. To stop automation:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.blinds.plist
   ```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python3 sun_position.py` | Full interactive analysis with timeline |
| `python3 sun_position.py auto` | Run automation (executes Shortcut) |
| `python3 sun_position.py auto-dry` | Show what would run without executing |
| `python3 sun_position.py status` | One-line status summary |
| `python3 sun_position.py config` | Show current configuration |
| `python3 sun_position.py json` | Output all data as JSON |
| `python3 sun_position.py step` | Output just the step name |
| `python3 sun_position.py risk` | Output just the glare risk percentage |
| `python3 sun_position.py help` | Show help |

## Customizing Glare Response

You can adjust how aggressively the blinds respond to glare by editing these values in `sun_position.py`:

```python
# Blind range
DAY_BLIND_MIN_OPEN = 10      # Never fully close (keep some light)
DAY_BLIND_MAX_OPEN = 100     # Fully open when no glare

# Glare thresholds
GLARE_THRESHOLD_LOW = 20     # Below this: blinds stay fully open
GLARE_THRESHOLD_HIGH = 100   # At this level: blinds at minimum

# Response curve (1.0 = linear)
# Values < 1.0 = gentler response (more light)
# Values > 1.0 = aggressive response (closes faster)
GLARE_RESPONSE_CURVE = 1.0
```

## Troubleshooting

**Shortcut not found:**
- Ensure the Shortcut is named exactly `Reduce Glare`
- Test running it manually: `shortcuts run "Reduce Glare" <<< "moderate"`

**Wrong glare calculations:**
- Verify your latitude/longitude are correct
- Check your window azimuth with a compass
- Run `python3 sun_position.py` to see detailed analysis

**LaunchAgent not running:**
- Check the log file for errors
- Verify paths in the plist are absolute paths
- Ensure Python 3.9+ is at `/usr/bin/python3`

## How Glare is Calculated

The glare model uses three factors:

1. **Sun Altitude (50% weight):** Low sun (< 10°) creates maximum glare as it streams in at eye level
2. **Entry Angle (25% weight):** How directly sunlight enters through the window
3. **Azimuth Alignment (25% weight):** Whether the sun is positioned to shine through your window at a problematic angle

These factors combine to produce a glare risk percentage (0-100%), which is then mapped to the five discrete levels.

## License

MIT License - Feel free to use and modify.
