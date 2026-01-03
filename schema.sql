-- A heirarchal structure where a MacroCycle is made up of N MiniCycles
-- which is made up of M Workouts and X Exercises.
-- Example: Winter cycle made up of 6 weeks, 4 workouts per week.
-- 1. THE LIBRARIES (The Global Catalog)
-- 1. Create a dedicated table for Body Parts.
CREATE TABLE IF NOT EXISTS Categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE -- 'Chest', 'Back', 'Quads', etc.
);
-- 2. The ExerciseLibrary.
CREATE TABLE IF NOT EXISTS ExerciseLibrary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE, 
    default_notes TEXT
);
-- 3. Connect exercises to their categories.
CREATE TABLE IF NOT EXISTS ExerciseCategories (
    exercise_id INTEGER,
    category_id INTEGER,
    PRIMARY KEY (exercise_id, category_id),
    FOREIGN KEY (exercise_id) REFERENCES ExerciseLibrary(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE CASCADE
);
-- 4. The Set/Rep Schemes --
CREATE TABLE IF NOT EXISTS RepSchemeLibrary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    reps_json TEXT,  
    weight_json TEXT 
);

-- 2. THE BLUEPRINT (The 6-Week Plan Hierarchy)
CREATE TABLE IF NOT EXISTS MacroCycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS MiniCycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    macro_id INTEGER,
    name TEXT,
    notes TEXT,
    FOREIGN KEY(macro_id) REFERENCES MacroCycles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mini_id INTEGER,
    name TEXT,
    notes TEXT,
    FOREIGN KEY(mini_id) REFERENCES MiniCycles(id) ON DELETE CASCADE
);

-- This replaces the "Exercises" table for planning. 
-- It is the "Blueprint" for what you SHOULD do.
CREATE TABLE IF NOT EXISTS ExerciseTemplates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER,
    exercise_name TEXT,
    target_reps_json TEXT,   -- Stores e.g., "[10, 8, 6]"
    target_weights_json TEXT, -- Stores e.g., "[100, 110, 120]"
    notes TEXT,
    FOREIGN KEY (workout_id) REFERENCES Workouts(id) ON DELETE CASCADE

);

-- 3. THE LOGS (The History / Actual Performance)
CREATE TABLE IF NOT EXISTS WorkoutLogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER, -- Links to the "Blueprint" Workout
    completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    overall_notes TEXT,
    FOREIGN KEY(workout_id) REFERENCES Workouts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS SetLogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_log_id INTEGER,
    exercise_template_id INTEGER, -- Links back to the planned Exercise
    set_number INTEGER,
    weight REAL,
    reps INTEGER,
    rpe INTEGER,
    notes TEXT,
    FOREIGN KEY(workout_log_id) REFERENCES WorkoutLogs(id) ON DELETE CASCADE,
    FOREIGN KEY(exercise_template_id) REFERENCES ExerciseTemplates(id) ON DELETE SET NULL
);