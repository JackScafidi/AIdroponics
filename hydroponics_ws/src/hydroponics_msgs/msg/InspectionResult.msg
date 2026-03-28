std_msgs/Header header
PlantPositionState[] plants       # array of 4 plant states
uint32 scan_number
bool disease_detected
string disease_type
string[] deficiency_trends        # channel-level: ["nitrogen"] if >50% show it
