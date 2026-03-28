std_msgs/Header header
string system_state               # STARTUP, RUNNING, PAUSED, ERROR
string active_node_path           # e.g. "MainSequence/ScheduledInspection/TriggerInspection"
string[] running_nodes
string[] failed_nodes
