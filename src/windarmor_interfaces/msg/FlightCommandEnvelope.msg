# The sole normal Flight actuator transport. Owners validate it independently.
builtin_interfaces/Time stamp
uint64 authority_epoch
uint64 generation
uint64 command_sequence
uint64 state_sequence
bool request_safe_stop

# Empty for safe-stop. Names and positions are parallel arrays.
string[] motor_names
float64[] motor_positions_rad

# False for safe-stop; numeric fields must then be ignored.
bool fan_commands_present
float64 fan_left
float64 fan_right
