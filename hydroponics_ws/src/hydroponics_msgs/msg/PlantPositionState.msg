uint8 position_index              # 0-3
string plant_id                   # unique plant instance ID (UUID)
string plant_profile              # "parsley", "basil", etc.
string status                     # EMPTY, SEEDLING, VEGETATIVE, MATURE, HARVESTED, SPENT
string health_state               # healthy, nitrogen_deficiency, phosphorus_deficiency, potassium_deficiency, iron_deficiency, disease_fungal, disease_bacterial
float64 canopy_area_cm2
float64 height_cm
uint32 leaf_count
uint32 days_since_planted
uint32 cut_cycle_number
builtin_interfaces/Time last_inspection
builtin_interfaces/Time last_harvest
