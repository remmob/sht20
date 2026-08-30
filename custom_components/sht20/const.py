"""Constants for the SHT20 Modbus integration"""

# Integration domain
DOMAIN = "sht20"

# Config entry keys
CONF_NAME = "name"
CONF_MODE = "mode"
CONF_DEVICE = "device"          # RTU only
CONF_DEVICE_ID = "device_id"    # Modbus unit ID
CONF_BAUDRATE = "baudrate"      # RTU only
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PORT = "port"              # TCP only
CONF_TEMP_OFFSET = "temp_offset"
CONF_HUM_OFFSET = "hum_offset"
CONF_MULTIPLIER = "multiplier"
CONF_PRESSURE = "pressure"      # Ambient pressure in hPa, used by the calculated sensors

# Connection error notifications
CONF_NOTIFY_CONNECTION_ERRORS_MOBILE = "notify_connection_errors_mobile"
CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT = "notify_connection_errors_persistent"
CONF_NOTIFY_CONNECTION_ERRORS_SERVICES = "notify_connection_errors_services"
CONF_CONNECTION_ERROR_NOTIFICATION_TITLE = "connection_error_notification_title"
CONF_CONNECTION_ERROR_DELAY = "connection_error_delay"
CONF_NOTIFY_RECOVERY = "notify_recovery"

# Quiet hours: hold mobile notifications during a configurable period
CONF_QUIET_HOURS_ENABLED = "quiet_hours_enabled"
CONF_QUIET_HOURS_START = "quiet_hours_start"
CONF_QUIET_HOURS_END = "quiet_hours_end"

# Default values
DEFAULT_NAME = "sht20"
DEFAULT_PORT = 502
DEFAULT_DEVICE_ID = 1
DEFAULT_BAUDRATE = 9600
DEFAULT_SCAN_INTERVAL = 10

# The sensor stores the baud rate as a code in its settings register
BAUDRATE_CODES = {0: 9600, 1: 14400, 2: 19200}
BAUDRATE_VALUES = {baudrate: code for code, baudrate in BAUDRATE_CODES.items()}
DEFAULT_MULTIPLIER = 0.01     # The sensor reports hundredths (2572 -> 25.72)

# Number of decimals shown for every sensor
DISPLAY_PRECISION = 2

# The humidity ratio is a small number, so it needs more decimals to be useful
ABSOLUTE_HUMIDITY_PRECISION = 5

# Notification defaults. Everything is off unless it is switched on explicitly.
DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE = False
DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT = False
DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES = ""
DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE = "SHT20 verbindingsfout!"
# ConnectionMonitor derives the failure threshold as max(1, int(delay / scan_interval)).
# 180 gives 3 cycles at a 60s scan_interval while staying generous at faster intervals.
# This is only the default; an existing config entry keeps its own stored value.
DEFAULT_CONNECTION_ERROR_DELAY = 180    # Seconds of failure before notifying
DEFAULT_NOTIFY_RECOVERY = True

DEFAULT_QUIET_HOURS_ENABLED = False
DEFAULT_QUIET_HOURS_START = "23:00:00"
DEFAULT_QUIET_HOURS_END = "07:00:00"

# Communication robustness
# modbus-connection reconnects automatically but does not retry timeouts, so
# MAX_READ_RETRIES/RETRY_DELAY_SECONDS provide our own retry. See
# _update_with_retry in hub.py.
MAX_READ_RETRIES = 3
RETRY_DELAY_SECONDS = 1

# This many consecutive timeouts means a stuck link: the socket is still open
# but the device behind it has stopped responding, so automatic reconnection
# has nothing to reconnect. See _consecutive_timeouts handling in hub.py.
STUCK_LINK_TIMEOUTS = 3
DEFAULT_PRESSURE = 1013.25      # Standard atmosphere at sea level

# Units for the calculated sensors
UNIT_ABSOLUTE_HUMIDITY = "kg/kg"
UNIT_ENTHALPY = "kJ/kg"

# Platforms to set up
PLATFORMS = ["sensor"]

# Minimum required Home Assistant version
REQUIRED_VERSION = "2025.6.0"
