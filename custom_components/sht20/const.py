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
# UITLEG: was 60. ConnectionMonitor rekent de drempel uit als
# max(1, int(delay / scan_interval)). Met de standaard scan_interval van 10 was
# 60 nog zes cycli, maar wie zijn scan_interval op 60 zet kwam uit op één: dan
# is één hapering al genoeg voor een melding. 180 geeft drie cycli bij een
# scan_interval van 60, en blijft ruim bij snellere intervallen.
#
# Let op: dit is de STANDAARD. Een bestaande config entry die deze optie al
# opgeslagen heeft, houdt zijn eigen waarde; die moet via het optiescherm.
DEFAULT_CONNECTION_ERROR_DELAY = 180    # Seconds of failure before notifying
DEFAULT_NOTIFY_RECOVERY = True

DEFAULT_QUIET_HOURS_ENABLED = False
DEFAULT_QUIET_HOURS_START = "23:00:00"
DEFAULT_QUIET_HOURS_END = "07:00:00"

# Communication robustness
# UITLEG: MAX_READ_RETRIES en RETRY_DELAY_SECONDS worden nog steeds gebruikt.
# modbus-connection herverbindt wel automatisch, maar herprobeert een time-out
# NIET ("Neither backend retries timeouts, dropped links, or other exception
# responses"). Zonder eigen retry zou één hapering meteen een verbindingsfout
# melden. Zie _update_with_retry in hub.py.
#
# STALE_CONNECTION_SECONDS wordt NIET meer gebruikt: het forceren van een
# reconnect na vijf minuten stilte was een pleister op zelfbeheerde clients.
# Mag weg bij het opschonen voor de release.
MAX_READ_RETRIES = 3
RETRY_DELAY_SECONDS = 1
STALE_CONNECTION_SECONDS = 300          # Force a reconnect after this long without data
DEFAULT_PRESSURE = 1013.25      # Standard atmosphere at sea level

# Units for the calculated sensors
UNIT_ABSOLUTE_HUMIDITY = "kg/kg"
UNIT_ENTHALPY = "kJ/kg"

# Platforms to set up
PLATFORMS = ["sensor"]

# Minimum required Home Assistant version
REQUIRED_VERSION = "2025.6.0"
