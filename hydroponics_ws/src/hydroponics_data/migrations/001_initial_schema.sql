CREATE TABLE IF NOT EXISTS plants (
    plant_id TEXT PRIMARY KEY,
    position_index INTEGER NOT NULL,
    plant_profile TEXT NOT NULL,
    planted_date REAL NOT NULL,
    current_stage TEXT NOT NULL DEFAULT 'seedling',
    status TEXT NOT NULL DEFAULT 'SEEDLING',
    cut_cycle_number INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inspections (
    inspection_id TEXT PRIMARY KEY,
    plant_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    canopy_area_cm2 REAL,
    height_cm REAL,
    leaf_count INTEGER,
    health_class TEXT,
    deficiency_type TEXT,
    maturity_state TEXT,
    raw_image_paths TEXT,
    FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
);
CREATE TABLE IF NOT EXISTS harvests (
    harvest_id TEXT PRIMARY KEY,
    plant_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    harvest_type TEXT NOT NULL,
    weight_grams REAL NOT NULL DEFAULT 0.0,
    cut_cycle_number INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
);
CREATE TABLE IF NOT EXISTS nutrient_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    ph REAL,
    ec REAL,
    temperature_c REAL,
    growth_stage TEXT,
    a_b_ratio REAL,
    ph_pid_output REAL,
    ec_pid_output REAL
);
CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    details TEXT
);
CREATE TABLE IF NOT EXISTS light_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    intensity_percent REAL,
    schedule_state TEXT,
    cumulative_watt_hours REAL DEFAULT 0.0
);
