# Read-only DRY_RUN preview. Actuator nodes must not consume this as a command.
builtin_interfaces/Time stamp
uint64 state_sequence
bool request_safe_stop

# Empty for a safe-stop preview. Names and positions are parallel arrays.
string[] motor_names
float64[] motor_positions_rad

# False for a safe-stop preview; numeric fields must then be ignored.
bool fan_commands_present
float64 fan_left
float64 fan_right
