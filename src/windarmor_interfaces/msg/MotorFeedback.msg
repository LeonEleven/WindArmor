# Configured logical identity. logical_name is not a mechanical-axis claim.
string logical_name
uint32 can_id

# False means no physical feedback values in this message are usable.
bool has_feedback

# ROS messages cannot carry Python None. Each physical value therefore has an
# explicit presence flag; consumers must ignore the numeric field when false.
bool position_valid
float64 position_rad
bool velocity_valid
float64 velocity_rad_s
bool torque_valid
float64 torque_nm
bool temperature_valid
float64 temperature_c
bool device_mode_valid
uint8 device_mode
bool fault_flags_valid
uint32 fault_flags

# Age at snapshot creation. Meaningful only when has_feedback is true.
float64 feedback_age_sec

# Adapter-evaluated status; no field is inferred from an absent measurement.
bool valid
bool fresh
bool healthy
