std_msgs/Header header
float64 ph_current
float64 ec_current
float64 temperature_c
float64 ph_target
float64 ec_target
float64 ph_pid_output
float64 ec_pid_output
float64 a_b_ratio
string growth_stage
uint32 days_since_planting
bool[4] pump_active               # [ph_up, ph_down, nutrient_a, nutrient_b]
