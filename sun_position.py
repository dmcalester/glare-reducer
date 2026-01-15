#!/usr/bin/env python3
"""
Sun position calculator for blinds automation.
Calculates solar azimuth and altitude for a given location and time.
"""

import json
import math
import plistlib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

# =============================================================================
# CONFIGURATION
# =============================================================================
# Config is stored in ~/Library/Preferences/com.blinds.plist
# Run "python3 sun_position.py config-init" to create initial config
# Run "python3 sun_position.py config" to view current settings

CONFIG_FILE = Path.home() / "Library" / "Preferences" / "com.blinds.plist"
HORIZON_PROFILE_FILE = Path(__file__).parent / "horizon_profile.json"

# Default configuration values
DEFAULT_CONFIG = {
    # Location
    "latitude": 40.7128,
    "longitude": -74.4717,
    "elevation": 0,  # feet above sea level
    "timezone": "America/New_York",
    # Room setup
    "window_azimuth": 90,  # degrees, direction window faces (0=N, 90=E, 180=S, 270=W)
    "monitor_facing": 180,  # degrees, direction monitor faces
    "user_facing": 270,  # degrees, direction you face when working
    # Manual terrain obstructions (optional, supplements GIS data)
    # Each entry: {"azimuth_start": 90, "azimuth_end": 160, "min_altitude": 12}
    "horizon_obstructions": [],
    # Blind settings
    "day_blind_min_open": 10,
    "day_blind_max_open": 100,
    "glare_threshold_low": 20,
    "glare_threshold_high": 100,
    "glare_response_curve": 1.0,
    # Shortcuts integration
    "blind_shortcut": "Reduce Glare",
    "blind_steps": [
        {"threshold": 0, "name": "severe"},
        {"threshold": 45, "name": "high"},
        {"threshold": 60, "name": "moderate"},
        {"threshold": 80, "name": "low"},
        {"threshold": 95, "name": "none"},
    ],
}


def load_config() -> dict:
    """Load configuration from plist file, with defaults for missing values."""
    config = DEFAULT_CONFIG.copy()

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "rb") as f:
                user_config = plistlib.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"Warning: Could not load config from {CONFIG_FILE}: {e}")

    return config


def save_config(config: dict):
    """Save configuration to plist file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        plistlib.dump(config, f)


def get_config_value(key: str, default=None):
    """Get a single config value."""
    config = load_config()
    return config.get(key, default)


# Load config at module level for convenience
_config = load_config()

LATITUDE = _config["latitude"]
LONGITUDE = _config["longitude"]
ELEVATION = _config["elevation"]
TIMEZONE = _config["timezone"]
WINDOW_AZIMUTH = _config["window_azimuth"]
MONITOR_FACING = _config["monitor_facing"]
USER_FACING = _config["user_facing"]
HORIZON_OBSTRUCTIONS = [
    (o["azimuth_start"], o["azimuth_end"], o["min_altitude"])
    for o in _config.get("horizon_obstructions", [])
]

# -----------------------------------------------------------------------------
# BLIND SETTINGS (loaded from config)
# -----------------------------------------------------------------------------
DAY_BLIND_MIN_OPEN = _config["day_blind_min_open"]
DAY_BLIND_MAX_OPEN = _config["day_blind_max_open"]
GLARE_THRESHOLD_LOW = _config["glare_threshold_low"]
GLARE_THRESHOLD_HIGH = _config["glare_threshold_high"]
GLARE_RESPONSE_CURVE = _config["glare_response_curve"]

# Shortcuts integration
BLIND_SHORTCUT = _config["blind_shortcut"]
BLIND_STEPS = [(s["threshold"], s["name"]) for s in _config["blind_steps"]]
VALID_STEPS = {s["name"] for s in _config["blind_steps"]}

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


def is_sun_blocked_by_terrain(sun_az: float, sun_alt: float) -> bool:
    """
    Check if sun is blocked by terrain obstructions (hills, buildings).
    First checks auto-calculated horizon profile, then falls back to manual HORIZON_OBSTRUCTIONS.
    """
    # Try auto-calculated horizon profile first
    horizon = load_horizon_profile()
    if horizon:
        # Find the closest azimuth in the profile
        az_key = str(round(sun_az / 5) * 5 % 360)  # Round to nearest 5°
        if az_key in horizon:
            horizon_alt = horizon[az_key]
            if sun_alt < horizon_alt:
                return True
            return False  # Sun is above horizon profile

    # Fall back to manual obstructions
    for az_start, az_end, min_alt in HORIZON_OBSTRUCTIONS:
        # Handle ranges that wrap around 360°
        if az_start <= az_end:
            in_range = az_start <= sun_az <= az_end
        else:
            in_range = sun_az >= az_start or sun_az <= az_end

        if in_range and sun_alt < min_alt:
            return True
    return False


def load_horizon_profile() -> Optional[Dict]:
    """Load cached horizon profile if it exists."""
    if HORIZON_PROFILE_FILE.exists():
        try:
            with open(HORIZON_PROFILE_FILE) as f:
                data = json.load(f)
                return data.get("horizon", {})
        except (json.JSONDecodeError, IOError):
            return None
    return None


def destination_point(
    lat: float, lon: float, bearing: float, distance_km: float
) -> Tuple[float, float]:
    """
    Calculate destination point given start point, bearing, and distance.
    Uses haversine formula.

    Args:
        lat, lon: Starting coordinates in degrees
        bearing: Bearing in degrees (0=N, 90=E, 180=S, 270=W)
        distance_km: Distance in kilometers

    Returns:
        tuple: (latitude, longitude) of destination point
    """
    R = 6371  # Earth's radius in km

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing)

    d = distance_km / R  # Angular distance

    dest_lat = math.asin(
        math.sin(lat_rad) * math.cos(d)
        + math.cos(lat_rad) * math.sin(d) * math.cos(bearing_rad)
    )

    dest_lon = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(d) * math.cos(lat_rad),
        math.cos(d) - math.sin(lat_rad) * math.sin(dest_lat),
    )

    return math.degrees(dest_lat), math.degrees(dest_lon)


def query_elevations(locations: List[Tuple[float, float]]) -> List[Optional[float]]:
    """
    Query Open-Elevation API for multiple locations.

    Args:
        locations: List of (lat, lon) tuples

    Returns:
        List of elevations in meters (or None for failed queries)
    """
    if not locations:
        return []

    # Build request payload
    payload = {
        "locations": [{"latitude": lat, "longitude": lon} for lat, lon in locations]
    }

    try:
        req = urllib.request.Request(
            "https://api.open-elevation.com/api/v1/lookup",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
            return [r.get("elevation") for r in data.get("results", [])]

    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  Error querying elevation API: {e}")
        return [None] * len(locations)


def calculate_horizon_profile(
    lat: float = LATITUDE,
    lon: float = LONGITUDE,
    observer_elevation: float = ELEVATION,
    azimuth_step: int = 5,
    distances_km: List[float] = None,
) -> Dict[str, float]:
    """
    Calculate horizon profile by sampling elevations in all directions.

    Args:
        lat, lon: Observer location
        observer_elevation: Observer elevation in feet
        azimuth_step: Degrees between azimuth samples (default 5°)
        distances_km: Distances to sample at (default [0.1, 0.25, 0.5, 1, 2, 5, 10])

    Returns:
        Dict mapping azimuth (as string) to horizon angle in degrees
    """
    if distances_km is None:
        distances_km = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]

    observer_elev_m = observer_elevation * 0.3048  # Convert feet to meters

    print(f"Calculating horizon profile for {lat:.4f}°N, {abs(lon):.4f}°W")
    print(f"Observer elevation: {observer_elevation} ft ({observer_elev_m:.0f} m)")
    print(
        f"Sampling {360 // azimuth_step} azimuths × {len(distances_km)} distances = {360 // azimuth_step * len(distances_km)} points"
    )
    print()

    # Build all sample points
    sample_points = []
    point_info = []  # (azimuth, distance_km)

    for azimuth in range(0, 360, azimuth_step):
        for dist in distances_km:
            dest_lat, dest_lon = destination_point(lat, lon, azimuth, dist)
            sample_points.append((dest_lat, dest_lon))
            point_info.append((azimuth, dist))

    # Query elevations in batches (API may have limits)
    print("Fetching elevation data from Open-Elevation API...")
    batch_size = 100
    all_elevations = []

    for i in range(0, len(sample_points), batch_size):
        batch = sample_points[i : i + batch_size]
        print(
            f"  Batch {i // batch_size + 1}/{(len(sample_points) + batch_size - 1) // batch_size}..."
        )
        elevations = query_elevations(batch)
        all_elevations.extend(elevations)

    # Calculate horizon angle for each azimuth
    horizon = {}

    for azimuth in range(0, 360, azimuth_step):
        max_angle = 0.0

        for i, (az, dist) in enumerate(point_info):
            if az != azimuth:
                continue

            elev = all_elevations[i]
            if elev is None:
                continue

            # Calculate angle to this point
            elev_diff = elev - observer_elev_m
            dist_m = dist * 1000

            # Angle = atan(elevation_difference / distance)
            angle = math.degrees(math.atan2(elev_diff, dist_m))
            max_angle = max(max_angle, angle)

        # Only store if there's meaningful obstruction (> 0.5°)
        horizon[str(azimuth)] = round(max(0, max_angle), 1)

    return horizon


def save_horizon_profile(horizon: dict, lat: float = LATITUDE, lon: float = LONGITUDE):
    """Save horizon profile to cache file."""
    data = {
        "generated": datetime.now().isoformat(),
        "location": {"latitude": lat, "longitude": lon, "elevation_ft": ELEVATION},
        "horizon": horizon,
    }

    with open(HORIZON_PROFILE_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved horizon profile to: {HORIZON_PROFILE_FILE}")


def print_horizon_profile(horizon: dict):
    """Print horizon profile in a readable format."""
    print("\n" + "=" * 70)
    print("Horizon Profile (minimum sun altitude to be visible)")
    print("=" * 70)

    # Find significant obstructions (> 2°)
    significant = {int(k): v for k, v in horizon.items() if v > 2}

    if not significant:
        print("No significant terrain obstructions detected.")
        print("The horizon is relatively flat in all directions.")
    else:
        print(f"\nSignificant obstructions (>{2}° horizon angle):\n")
        print(f"{'Azimuth':>10} {'Direction':>10} {'Horizon':>10}")
        print("-" * 35)

        for az in sorted(significant.keys()):
            direction = compass_direction(az)
            angle = significant[az]
            bar = "█" * int(angle / 2)
            print(f"{az:>10}° {direction:>10} {angle:>9.1f}° {bar}")

    # Print full profile in compact form
    print("\n" + "-" * 70)
    print("Full profile (azimuth: horizon angle):\n")

    line = ""
    for az in range(0, 360, 5):
        val = horizon.get(str(az), 0)
        line += f"{az:3d}°:{val:4.1f}  "
        if (az + 5) % 60 == 0:
            print(line)
            line = ""
    if line:
        print(line)

    print("=" * 70)


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

    # Check if sun is blocked by terrain (hills, buildings)
    if is_sun_blocked_by_terrain(sun_az, sun_alt):
        return {
            "status": "blocked_by_terrain",
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
    # At 0° = sun perpendicular to window (worst glare)
    # At 60°+ = sun at wide angle, minimal direct entry
    if entry_angle < 60:
        entry_factor = (60 - entry_angle) / 60
    else:
        entry_factor = 0.0

    # Combined glare risk - both factors must align for significant glare
    # Low sun streaming directly through window = worst case
    glare_risk = 100 * (
        0.5 * altitude_factor  # Low sun is critical
        + 0.5 * entry_factor  # Direct entry angle matters equally
    )

    # Boost when both factors align (multiplicative bonus)
    if altitude_factor > 0.5 and entry_factor > 0.5:
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
                    "blocked_by_terrain": " \u2587\u2587 ",
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
            obstructions_str = (
                "None"
                if not HORIZON_OBSTRUCTIONS
                else ", ".join(f"{s}°-{e}°: {a}°" for s, e, a in HORIZON_OBSTRUCTIONS)
            )
            horizon_status = "Yes" if HORIZON_PROFILE_FILE.exists() else "No"
            config_status = "Yes" if CONFIG_FILE.exists() else "No (using defaults)"
            print(f"""
Current Configuration
=====================
Config file: {CONFIG_FILE}
Config exists: {config_status}

Location:
  Latitude:   {LATITUDE:.4f}°N
  Longitude:  {abs(LONGITUDE):.4f}°W
  Elevation:  {ELEVATION} ft
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

Terrain:
  Manual obstructions: {obstructions_str}
  GIS horizon profile: {horizon_status}

To edit: open {CONFIG_FILE}
Or run: open -a "Property List Editor" "{CONFIG_FILE}"
""")

        elif mode == "config-init":
            # Initialize config file with current/default values
            if CONFIG_FILE.exists():
                print(f"Config file already exists: {CONFIG_FILE}")
                print("To reset, delete it first: rm '{CONFIG_FILE}'")
            else:
                save_config(DEFAULT_CONFIG)
                print(f"Created config file: {CONFIG_FILE}")
                print("\nYou can edit it with:")
                print(f"  open -a 'Property List Editor' '{CONFIG_FILE}'")
                print("  # or any text editor (it's XML format)")

        elif mode == "horizon":
            # Calculate and save horizon profile from GIS elevation data
            print("\n" + "=" * 70)
            print("Horizon Profile Calculator")
            print("Uses Open-Elevation API to detect hills/mountains blocking the sun")
            print("=" * 70 + "\n")

            horizon = calculate_horizon_profile()
            print_horizon_profile(horizon)
            save_horizon_profile(horizon)

            print(
                "\nThe horizon profile will now be used automatically for glare calculations."
            )
            print("Re-run this command if you move to a new location.")

        elif mode == "horizon-show":
            # Show existing horizon profile without recalculating
            horizon = load_horizon_profile()
            if horizon:
                print_horizon_profile(horizon)
            else:
                print(
                    "No horizon profile found. Run 'python3 sun_position.py horizon' to generate one."
                )

        elif mode == "help":
            print(f"""
Sun Position & Glare Calculator for Blinds Automation

Automatic Control (recommended):
  python3 sun_position.py auto      Run shortcut to set blinds automatically
  python3 sun_position.py auto-dry  Show what would run (no changes)

Manual/Debug:
  python3 sun_position.py           Full analysis (interactive)
  python3 sun_position.py status    One-line status
  python3 sun_position.py json      Full data as JSON
  python3 sun_position.py step      Step name only (severe/high/moderate/low/none)
  python3 sun_position.py day       Day blind open % (0-100)
  python3 sun_position.py risk      Glare risk % (0-100)

Configuration:
  python3 sun_position.py config      Show current configuration
  python3 sun_position.py config-init Create config file with defaults

Terrain/Horizon:
  python3 sun_position.py horizon      Calculate horizon from GIS elevation data
  python3 sun_position.py horizon-show Show saved horizon profile

Setup:
  1. Run 'config-init' to create the config file
  2. Edit config: open -a "Property List Editor" "{CONFIG_FILE}"
     - Set latitude, longitude, timezone for your location
     - Set window_azimuth, monitor_facing, user_facing for your room
  3. Create a Shortcut named 'Reduce Glare' that accepts text input
     - Input will be one of: severe, high, moderate, low, none
  4. (Optional) Run 'horizon' to auto-detect hills/mountains blocking sun
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
