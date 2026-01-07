#!/usr/bin/env python3
"""
Sun position calculator for blinds automation.
Calculates solar azimuth and altitude for a given location and time.
"""

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# =============================================================================
# CONFIGURATION - You must edit these values for your location and setup
# =============================================================================

# Your location - REQUIRED: Set these to your coordinates
# Find your coordinates: https://www.latlong.net/
# Northern latitudes are positive, Southern are negative
# Eastern longitudes are positive, Western are negative
LATITUDE = 40.7128  # Example: 40.7128 for New York City - UPDATE TO YOUR LOCATION
LONGITUDE = -74.0060  # Example: -74.0060 for New York City - UPDATE TO YOUR LOCATION
ELEVATION = 0  # feet above sea level (minor effect on calculations)
TIMEZONE = (
    "America/New_York"  # Your timezone, e.g., "America/New_York", "Europe/London"
)

# Room configuration - measure these with a compass app
WINDOW_AZIMUTH = 90  # degrees, direction your window faces (0=N, 90=E, 180=S, 270=W)
MONITOR_FACING = 180  # degrees, direction your monitor screen faces
USER_FACING = 270  # degrees, direction you face when working

# -----------------------------------------------------------------------------
# BLIND SETTINGS - Adjust these to change how blinds respond to glare
# -----------------------------------------------------------------------------

# Day blind range (open percentage)
DAY_BLIND_MIN_OPEN = 10  # Minimum open % (never fully closed, keep some light)
DAY_BLIND_MAX_OPEN = 100  # Maximum open % (fully retracted)

# Glare thresholds
GLARE_THRESHOLD_LOW = 20  # Below this: blinds fully open, no action needed
GLARE_THRESHOLD_HIGH = 100  # At this level: blinds at minimum open

# Advanced: Curve adjustment (1.0 = linear, <1 = gentler, >1 = more aggressive)
# Example: 0.7 = more light allowed, 1.3 = closes faster
GLARE_RESPONSE_CURVE = 1.0

# -----------------------------------------------------------------------------
# SHORTCUTS INTEGRATION - Maps glare levels to macOS Shortcuts
# You must create a Shortcut named "Reduce Glare" that accepts a text input
# The input will be one of: severe, high, moderate, low, none
# Your Shortcut should adjust blinds accordingly (e.g., via HomeKit)
# -----------------------------------------------------------------------------
BLIND_SHORTCUT = "Reduce Glare"  # Single shortcut, receives level as input
VALID_STEPS = {"severe", "high", "moderate", "low", "none"}

# Step thresholds (calculated day_open % -> glare level)
BLIND_STEPS = [
    (0, "severe"),  # Worst glare - blinds most closed
    (45, "high"),  # High glare
    (60, "moderate"),  # Moderate glare
    (80, "low"),  # Low glare
    (95, "none"),  # No glare - blinds fully open
]

# =============================================================================


def julian_day(dt: datetime) -> float:
    """Calculate Julian Day from datetime."""
    year = dt.year
    month = dt.month
    day = dt.day + dt.hour / 24 + dt.minute / 1440 + dt.second / 86400

    if month <= 2:
        year -= 1
        month += 12

    a = int(year / 100)
    b = 2 - a + int(a / 4)

    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5
    return jd


def sun_position(dt: datetime, lat: float, lon: float) -> tuple[float, float]:
    """
    Calculate sun position (azimuth and altitude) for a given time and location.

    Returns:
        tuple: (azimuth in degrees, altitude in degrees)
               azimuth: 0=North, 90=East, 180=South, 270=West
               altitude: 0=horizon, 90=zenith
    """
    # Convert to UTC for calculations
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
    dt_utc = dt.astimezone(timezone.utc)

    jd = julian_day(dt_utc)

    # Julian centuries from J2000.0
    t = (jd - 2451545.0) / 36525.0

    # Solar coordinates (simplified, accurate to ~0.01°)
    # Mean longitude of the sun
    l0 = (280.46646 + 36000.76983 * t + 0.0003032 * t**2) % 360

    # Mean anomaly of the sun
    m = (357.52911 + 35999.05029 * t - 0.0001537 * t**2) % 360
    m_rad = math.radians(m)

    # Equation of center
    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t**2) * math.sin(m_rad)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
        + 0.000289 * math.sin(3 * m_rad)
    )

    # Sun's true longitude
    sun_lon = l0 + c

    # Sun's apparent longitude (corrected for nutation and aberration)
    omega = 125.04 - 1934.136 * t
    sun_apparent_lon = sun_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    # Obliquity of ecliptic
    obliquity = 23.439291 - 0.0130042 * t
    obliquity_rad = math.radians(obliquity)

    # Sun's right ascension and declination
    sun_apparent_lon_rad = math.radians(sun_apparent_lon)

    ra = math.atan2(
        math.cos(obliquity_rad) * math.sin(sun_apparent_lon_rad),
        math.cos(sun_apparent_lon_rad),
    )

    declination = math.asin(math.sin(obliquity_rad) * math.sin(sun_apparent_lon_rad))

    # Greenwich Mean Sidereal Time
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t**2
        - t**3 / 38710000
    ) % 360

    # Local Sidereal Time
    lst = math.radians((gmst + lon) % 360)

    # Hour angle
    ha = lst - ra

    # Convert latitude to radians
    lat_rad = math.radians(lat)

    # Altitude (elevation)
    sin_alt = math.sin(lat_rad) * math.sin(declination) + math.cos(lat_rad) * math.cos(
        declination
    ) * math.cos(ha)
    altitude = math.degrees(math.asin(sin_alt))

    # Azimuth
    cos_az = (math.sin(declination) - math.sin(lat_rad) * sin_alt) / (
        math.cos(lat_rad) * math.cos(math.asin(sin_alt))
    )
    cos_az = max(-1, min(1, cos_az))  # Clamp to [-1, 1]

    azimuth = math.degrees(math.acos(cos_az))

    # Adjust azimuth based on hour angle
    if math.sin(ha) > 0:
        azimuth = 360 - azimuth

    return azimuth, altitude


def compass_direction(azimuth: float) -> str:
    """Convert azimuth to compass direction."""
    directions = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    index = round(azimuth / 22.5) % 16
    return directions[index]


def angle_difference(a1: float, a2: float) -> float:
    """Calculate the smallest angle between two azimuths."""
    diff = abs(a1 - a2) % 360
    return min(diff, 360 - diff)


def can_sun_enter_window(
    sun_az: float, sun_alt: float, window_az: float, window_fov: float = 140
) -> tuple[bool, float]:
    """
    Determine if sun can shine through window.

    Args:
        sun_az: Sun azimuth in degrees
        sun_alt: Sun altitude in degrees
        window_az: Direction window faces
        window_fov: Field of view of window (how wide the opening is), default 140°

    Returns:
        tuple: (can_enter: bool, entry_angle: float degrees from perpendicular)
    """
    if sun_alt <= 0:
        return False, 180

    # Sun must be in the hemisphere the window faces
    # Window facing 176° (S) can see sun from ~106° to ~246° (±70° from center)
    angle_from_window = angle_difference(sun_az, window_az)

    can_enter = angle_from_window <= (window_fov / 2)
    return can_enter, angle_from_window


def analyze_glare(
    sun_az: float,
    sun_alt: float,
    window_az: float = WINDOW_AZIMUTH,
    monitor_facing: float = MONITOR_FACING,
) -> dict:
    """
    Analyze glare on monitor from sun through window.

    Key insight: Low sun angle is the primary glare factor. When sun is below ~15°,
    it streams in at eye level and creates harsh direct/reflected glare on screens.
    """
    # Sun must be above horizon
    if sun_alt <= 0:
        return {
            "status": "night",
            "can_enter_window": False,
            "entry_angle": 0,
            "glare_risk": 0,
            "recommendation": "blinds_open",
        }

    # Check if sun can enter window
    can_enter, entry_angle = can_sun_enter_window(sun_az, sun_alt, window_az)

    if not can_enter:
        return {
            "status": "no_direct_sun",
            "can_enter_window": False,
            "entry_angle": round(entry_angle, 1),
            "glare_risk": 0,
            "recommendation": "blinds_open",
        }

    # GLARE MODEL
    # Factor 1: Sun altitude - LOW SUN IS THE KILLER
    # Below 10° = maximum glare (streaming rays at eye/monitor level)
    # 10-20° = decreasing glare
    # Above 25° = minimal glare (sun too high to stream in)
    if sun_alt < 10:
        altitude_factor = 1.0
    elif sun_alt < 25:
        altitude_factor = (25 - sun_alt) / 15
    else:
        altitude_factor = 0.0

    # Factor 2: Entry angle - how directly sun enters window
    # At 52° entry angle, sun still streams in effectively
    # Wider than 70° = sunlight doesn't really enter
    if entry_angle < 60:
        entry_factor = (60 - entry_angle) / 60
    else:
        entry_factor = 0.0

    # Factor 3: Azimuth alignment with problem zone
    # Worst glare is typically when sun is in SE (morning) shining through window
    # Adjust problem_zone_center based on your window orientation
    problem_zone_center = (
        WINDOW_AZIMUTH - 45
    ) % 360  # 45° before perpendicular to window
    azimuth_offset = angle_difference(sun_az, problem_zone_center)
    if azimuth_offset < 30:
        azimuth_factor = (30 - azimuth_offset) / 30
    else:
        azimuth_factor = 0.0

    # Combined glare risk - altitude is weighted most heavily
    # since low sun is the primary problem
    glare_risk = 100 * (
        0.5 * altitude_factor  # Low sun is most important
        + 0.25 * entry_factor  # Entry angle matters
        + 0.25 * azimuth_factor  # Azimuth alignment
    )

    # Boost when all factors align (multiplicative bonus)
    if altitude_factor > 0.5 and entry_factor > 0.3 and azimuth_factor > 0.3:
        glare_risk = min(100, glare_risk * 1.3)

    glare_risk = min(100, max(0, glare_risk))

    # Determine status and recommendation
    if glare_risk > 60:
        status = "high_glare"
        recommendation = "blinds_closed"
    elif glare_risk > 35:
        status = "moderate_glare"
        recommendation = "blinds_partial"
    else:
        status = "low_glare"
        recommendation = "blinds_open"

    return {
        "status": status,
        "can_enter_window": True,
        "entry_angle": round(entry_angle, 1),
        "sun_altitude": round(sun_alt, 1),
        "glare_risk": round(glare_risk, 1),
        "recommendation": recommendation,
    }


def print_sun_info(dt: datetime = None):
    """Print current sun position and glare analysis."""
    if dt is None:
        dt = datetime.now(ZoneInfo(TIMEZONE))

    azimuth, altitude = sun_position(dt, LATITUDE, LONGITUDE)
    glare = analyze_glare(azimuth, altitude)

    print(f"\n{'=' * 60}")
    print(f"Sun Position - {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"{'=' * 60}")
    print(f"Location: {LATITUDE:.4f}°N, {abs(LONGITUDE):.4f}°W")
    print(f"{'=' * 60}")
    print(f"Room Setup:")
    print(f"  Window faces:  {WINDOW_AZIMUTH}° ({compass_direction(WINDOW_AZIMUTH)})")
    print(f"  Monitor faces: {MONITOR_FACING}° ({compass_direction(MONITOR_FACING)})")
    print(f"  User faces:    {USER_FACING}° ({compass_direction(USER_FACING)})")
    print(f"{'=' * 60}")
    print(f"Sun Azimuth:  {azimuth:6.1f}° ({compass_direction(azimuth)})")
    print(f"Sun Altitude: {altitude:6.1f}°", end="")
    if altitude <= 0:
        print(" (below horizon)")
    elif altitude < 10:
        print(" (very low)")
    elif altitude < 30:
        print(" (low)")
    else:
        print()
    print(f"{'=' * 60}")
    print(f"Glare Analysis:")
    print(f"  Can enter window: {'Yes' if glare['can_enter_window'] else 'No'}")
    if glare["can_enter_window"]:
        print(f"  Entry angle:      {glare['entry_angle']:.1f}° from perpendicular")
    print(f"  Glare Risk:       {glare['glare_risk']:.1f}%")
    print(f"  Status:           {glare['status']}")
    print(f"{'=' * 60}")

    # Calculate blind position
    day_open = calculate_day_blind(glare["glare_risk"])
    step = get_blind_step(day_open)

    print(f"Blind Recommendation:")
    print(f"  Position: {day_open}% open  ({step})")
    print(f"{'=' * 60}\n")

    return azimuth, altitude, glare


def show_morning_timeline(date: datetime = None):
    """Show sun positions throughout the morning with blind recommendations."""
    if date is None:
        date = datetime.now(ZoneInfo(TIMEZONE))

    print(f"\n{'=' * 85}")
    print(f"Morning Timeline - {date.strftime('%Y-%m-%d')}")
    print(
        f"Window: {WINDOW_AZIMUTH}° ({compass_direction(WINDOW_AZIMUTH)}) | "
        f"Monitor: {MONITOR_FACING}° ({compass_direction(MONITOR_FACING)})"
    )
    print(f"{'=' * 85}")
    print(
        f"{'Time':>8} | {'Sun':>12} | {'Alt':>6} | {'Glare':>7} | {'Day':>5} | {'Step':<14} | Status"
    )
    print(f"{'-' * 85}")

    for hour in range(5, 13):
        for minute in [0, 30]:
            dt = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            az, alt = sun_position(dt, LATITUDE, LONGITUDE)
            glare = analyze_glare(az, alt)

            if alt > -5:  # Show from just before sunrise
                day_open = calculate_day_blind(glare["glare_risk"])
                step = get_blind_step(day_open)

                status_icon = {
                    "night": "    ",
                    "no_direct_sun": " -- ",
                    "low_glare": " OK ",
                    "moderate_glare": " !! ",
                    "high_glare": ">>>>",
                }.get(glare["status"], "")

                print(
                    f"{dt.strftime('%H:%M'):>8} | {az:5.0f}° {compass_direction(az):>4} | "
                    f"{alt:5.1f}° | {glare['glare_risk']:5.1f}% | {day_open:>3}% | {step:<14} | {status_icon} {glare['status']}"
                )

    print(f"{'=' * 85}\n")


def show_yearly_glare_windows():
    """Show when glare occurs throughout the year."""
    print(f"\n{'=' * 75}")
    print("Yearly Glare Analysis - When to close blinds")
    print(f"{'=' * 75}")
    print(
        f"{'Month':>10} | {'Glare Start':>12} | {'Glare End':>12} | {'Duration':>10} | Peak Risk"
    )
    print(f"{'-' * 75}")

    current_year = datetime.now().year
    for month in range(1, 13):
        # Use 15th of each month
        date = datetime(current_year, month, 15, tzinfo=ZoneInfo(TIMEZONE))
        month_name = date.strftime("%B")

        glare_start = None
        glare_end = None
        peak_risk = 0
        peak_time = None

        # Check every 15 minutes from 5 AM to 12 PM
        for hour in range(5, 13):
            for minute in range(0, 60, 15):
                dt = date.replace(hour=hour, minute=minute)
                az, alt = sun_position(dt, LATITUDE, LONGITUDE)
                glare = analyze_glare(az, alt)

                if glare["glare_risk"] > peak_risk:
                    peak_risk = glare["glare_risk"]
                    peak_time = dt

                if glare["glare_risk"] > 50:  # Significant glare
                    if glare_start is None:
                        glare_start = dt
                    glare_end = dt

        if glare_start and glare_end:
            duration_mins = (glare_end - glare_start).seconds // 60
            duration_str = f"{duration_mins // 60}h {duration_mins % 60}m"
            print(
                f"{month_name:>10} | {glare_start.strftime('%H:%M'):>12} | "
                f"{glare_end.strftime('%H:%M'):>12} | {duration_str:>10} | "
                f"{peak_risk:.0f}% @ {peak_time.strftime('%H:%M')}"
            )
        else:
            print(
                f"{month_name:>10} | {'--':>12} | {'--':>12} | {'--':>10} | "
                f"{peak_risk:.0f}%"
            )

    print(f"{'=' * 75}\n")


def calculate_day_blind(glare_risk: float) -> int:
    """
    Calculate day blind open percentage based on glare risk.
    Uses configuration values from top of file.

    Returns:
        int: day_blind_open_percent (0-100)
    """
    if glare_risk < GLARE_THRESHOLD_LOW:
        # No significant glare - blinds fully open
        return DAY_BLIND_MAX_OPEN

    # Calculate day blind position using configured curve
    # Map glare from [THRESHOLD_LOW, THRESHOLD_HIGH] to [MAX_OPEN, MIN_OPEN]
    glare_range = GLARE_THRESHOLD_HIGH - GLARE_THRESHOLD_LOW
    open_range = DAY_BLIND_MAX_OPEN - DAY_BLIND_MIN_OPEN

    # Normalized glare (0 to 1)
    normalized = (glare_risk - GLARE_THRESHOLD_LOW) / glare_range
    normalized = max(0, min(1, normalized))  # Clamp to 0-1

    # Apply curve adjustment
    if GLARE_RESPONSE_CURVE != 1.0:
        normalized = normalized**GLARE_RESPONSE_CURVE

    # Calculate open percentage (higher glare = lower open)
    day_open = int(DAY_BLIND_MAX_OPEN - (normalized * open_range))
    day_open = max(DAY_BLIND_MIN_OPEN, min(DAY_BLIND_MAX_OPEN, day_open))

    return day_open


def get_blind_step(day_open: int) -> str:
    """
    Convert day blind percentage to a discrete step name for Shortcuts.
    """
    for threshold, name in reversed(BLIND_STEPS):
        if day_open >= threshold:
            return name
    return BLIND_STEPS[0][1]  # Default to first step


def run_blind_shortcut(step: str, dry_run: bool = False) -> tuple[bool, str]:
    """
    Run the macOS Shortcut for the given step.

    Args:
        step: Glare level - one of: severe, high, moderate, low, none

    Returns:
        tuple: (success: bool, message: str)
    """
    import subprocess

    if step not in VALID_STEPS:
        return False, f"Unknown step: {step}"

    if dry_run:
        return (
            True,
            f'[DRY RUN] Would run: shortcuts run "{BLIND_SHORTCUT}" with input "{step}"',
        )

    try:
        result = subprocess.run(
            ["shortcuts", "run", BLIND_SHORTCUT],
            input=step,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, f"Ran '{BLIND_SHORTCUT}' with level '{step}'"
        else:
            return False, f"Shortcut failed: {result.stderr.strip() or 'unknown error'}"
    except subprocess.TimeoutExpired:
        return False, "Shortcut timed out"
    except FileNotFoundError:
        return False, "shortcuts command not found"
    except Exception as e:
        return False, f"Error: {e}"


def get_blinds_recommendation() -> dict:
    """Get current blinds recommendation - for automation use."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    az, alt = sun_position(now, LATITUDE, LONGITUDE)
    glare = analyze_glare(az, alt)

    day_open = calculate_day_blind(glare["glare_risk"])
    step = get_blind_step(day_open)

    return {
        "timestamp": now.isoformat(),
        "sun_azimuth": round(az, 1),
        "sun_altitude": round(alt, 1),
        "glare_risk": glare["glare_risk"],
        "status": glare["status"],
        "day_open": day_open,
        "step": step,
    }


if __name__ == "__main__":
    import json
    import sys

    # CLI modes
    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == "auto":
            # Automatically adjust blinds by running the appropriate Shortcut
            result = get_blinds_recommendation()
            step = result["step"]
            success, message = run_blind_shortcut(step)
            timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"[{timestamp}] {message} (glare: {result['glare_risk']:.0f}%, step: {step})"
            )
            sys.exit(0 if success else 1)

        elif mode == "auto-dry":
            # Dry run - show what would happen without running shortcuts
            result = get_blinds_recommendation()
            step = result["step"]
            success, message = run_blind_shortcut(step, dry_run=True)
            print(message)

        elif mode == "step":
            # Step name for Shortcuts (use with If/Then)
            result = get_blinds_recommendation()
            print(result["step"])

        elif mode == "day":
            # Day blind open percentage
            result = get_blinds_recommendation()
            print(result["day_open"])

        elif mode == "json":
            # Full JSON output
            result = get_blinds_recommendation()
            print(json.dumps(result, indent=2))

        elif mode == "risk":
            # Just the risk percentage
            result = get_blinds_recommendation()
            print(int(result["glare_risk"]))

        elif mode == "status":
            # Human-readable one-liner
            result = get_blinds_recommendation()
            print(
                f"{result['step']} ({result['day_open']}% open, glare: {result['glare_risk']:.0f}%)"
            )

        elif mode == "config":
            # Show current configuration
            steps_str = ", ".join(f"{name}={thresh}%" for thresh, name in BLIND_STEPS)
            print(f"""
Current Configuration
=====================
Location:
  Latitude:   {LATITUDE:.4f}°N
  Longitude:  {abs(LONGITUDE):.4f}°W
  Timezone:   {TIMEZONE}

Room Setup:
  Window:     {WINDOW_AZIMUTH}° ({compass_direction(WINDOW_AZIMUTH)})
  Monitor:    {MONITOR_FACING}° ({compass_direction(MONITOR_FACING)})
  User:       {USER_FACING}° ({compass_direction(USER_FACING)})

Day Blind Settings:
  Range:           {DAY_BLIND_MIN_OPEN}% - {DAY_BLIND_MAX_OPEN}% open
  Glare threshold: {GLARE_THRESHOLD_LOW}% (low) - {GLARE_THRESHOLD_HIGH}% (high)
  Response curve:  {GLARE_RESPONSE_CURVE} (1.0=linear, <1=gentler, >1=aggressive)

Steps for Shortcuts:
  {steps_str}

Edit these values in: sun_position.py (configuration section at top)
""")

        elif mode == "help":
            print("""
Sun Position & Glare Calculator for Blinds Automation

Automatic Control (recommended):
  python3 sun_position.py auto      Run shortcut to set blinds automatically
  python3 sun_position.py auto-dry  Show what would run (no changes)

Manual/Debug:
  python3 sun_position.py           Full analysis (interactive)
  python3 sun_position.py status    One-line status
  python3 sun_position.py config    Show current configuration
  python3 sun_position.py json      Full data as JSON
  python3 sun_position.py step      Step name only (severe/high/moderate/low/none)
  python3 sun_position.py day       Day blind open % (0-100)
  python3 sun_position.py risk      Glare risk % (0-100)

Required Setup:
  1. Edit configuration at top of sun_position.py:
     - Set LATITUDE, LONGITUDE, TIMEZONE for your location
     - Set WINDOW_AZIMUTH, MONITOR_FACING, USER_FACING for your room
  2. Create a Shortcut named 'Reduce Glare' that accepts text input
     - Input will be one of: severe, high, moderate, low, none
     - Configure Shortcut to adjust your blinds accordingly

To adjust: edit BLIND SETTINGS at top of sun_position.py
""")
        else:
            print(f"Unknown mode: {mode}. Use 'help' for options.")
            sys.exit(1)
    else:
        # Interactive mode - full analysis
        print_sun_info()
        show_morning_timeline()
        show_yearly_glare_windows()

        print("\n>>> For Shortcuts automation, run: python3 sun_position.py help")
