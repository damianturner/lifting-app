import streamlit as st
import sqlite3
import logging
import sys
import io
import os
import json

# --- 1. LOGGING SETUP ---
def setup_logging():
    if "log_buffer" not in st.session_state:
        st.session_state.log_buffer = io.StringIO()

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        logger.handlers.clear()

    # Terminal Handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(stdout_handler)

    # Streamlit Buffer Handler
    buffer_handler = logging.StreamHandler(st.session_state.log_buffer)
    buffer_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(buffer_handler)
    
    return logger

# --- 2. DATABASE INITIALIZATION ---
@st.cache_resource
def init_db(db_path, _logger):
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        with open('schema.sql', 'r') as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        seed_library(conn, db_path) # Pass db_path here
        _logger.info("Database and Seed Data initialized successfully.")
    except Exception as e:
        _logger.error(f"Database Init Failed: {e}", exc_info=True)
    finally:
        conn.close()

# --- 3. DB SEEDING LOGIC ---
@st.cache_resource
def seed_library(_conn, db_path):
    cur = _conn.cursor()
    _logger = logging.getLogger() # Get a logger for seed_library

    # Define common categories
    common_categories = ["Chest", "Back", "Shoulders", "Biceps", "Triceps", "Quads", "Hamstrings", "Glutes", "Calves", "Core", "Forearms", "Full Body", "Upper Body", "Lower Body", "Push", "Pull", "Legs", "Compound", "Isolation"]
    for cat in common_categories:
        cur.execute("INSERT OR IGNORE INTO Categories (name) VALUES (?)", (cat,))
    _conn.commit()

    exercise_seed_data = {
        "Bench Press (Barbell)": {"notes": "", "categories": ["Chest", "Triceps", "Shoulders", "Compound", "Upper Body", "Push"]},
        "Pull Up": {"notes": "", "categories": ["Back", "Biceps", "Forearms", "Compound", "Upper Body", "Pull"]},
        "Deadlift": {"notes": "", "categories": ["Back", "Hamstrings", "Glutes", "Forearms", "Compound", "Full Body"]},
        "Squat (Barbell)": {"notes": "", "categories": ["Quads", "Glutes", "Hamstrings", "Compound", "Lower Body", "Legs"]},
        "Overhead Press (Barbell)": {"notes": "", "categories": ["Shoulders", "Triceps", "Compound", "Upper Body", "Push"]},
        "Bent-Over Row (Barbell)": {"notes": "", "categories": ["Back", "Biceps", "Compound", "Upper Body", "Pull"]},
        "Bicep Curl (Dumbbell)": {"notes": "", "categories": ["Biceps", "Isolation", "Upper Body", "Pull"]},
        "Tricep Extension (Dumbbell)": {"notes": "", "categories": ["Triceps", "Isolation", "Upper Body", "Push"]},
        "Leg Press": {"notes": "", "categories": ["Quads", "Glutes", "Hamstrings", "Compound", "Lower Body", "Legs"]},
        "Lateral Raise (Dumbbell)": {"notes": "", "categories": ["Shoulders", "Isolation", "Upper Body", "Push"]},
        "Romanian Deadlift (Barbell)": {"notes": "", "categories": ["Hamstrings", "Glutes", "Isolation", "Lower Body", "Legs"]},
        "Plank": {"notes": "", "categories": ["Core", "Isolation", "Full Body"]},
    }

    for ex_name, data in exercise_seed_data.items():
        # Use the updated insert_exercise_to_library function for seeding
        # It handles insertion into ExerciseLibrary, Categories (if new), and ExerciseCategories
        success = insert_exercise_to_library(db_path, ex_name, data["notes"], data["categories"], _logger=_logger)
        if not success:
            _logger.warning(f"Failed to seed exercise '{ex_name}' or it already exists.")
    
    _conn.commit()

def insert_exercise_to_library(db_path, exercise_name, default_notes="", category_names=None, _logger=None):
    if _logger is None:
        _logger = logging.getLogger() # Get a default logger if not provided

    if category_names is None:
        category_names = []

    conn = None
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cur = conn.cursor()

        # Insert into ExerciseLibrary
        cur.execute("INSERT OR IGNORE INTO ExerciseLibrary (name, default_notes) VALUES (?, ?)", (exercise_name, default_notes))
        exercise_id = cur.lastrowid
        _logger.info(f"Successfully added '{exercise_name}' to ExerciseLibrary with ID {exercise_id}.")

        # Handle categories
        for cat_name in category_names:
            # Insert category if it doesn't exist
            cur.execute("INSERT OR IGNORE INTO Categories (name) VALUES (?)", (cat_name.strip(),))
            # Get category ID
            cur.execute("SELECT id FROM Categories WHERE name = ?", (cat_name.strip(),))
            category_id = cur.fetchone()[0]
            
            # Link exercise and category
            cur.execute("INSERT OR IGNORE INTO ExerciseCategories (exercise_id, category_id) VALUES (?, ?)", (exercise_id, category_id))
            _logger.info(f"Linked exercise '{exercise_name}' (ID {exercise_id}) to category '{cat_name}' (ID {category_id}).")

        conn.commit()
        return True
    except sqlite3.IntegrityError:
        _logger.warning(f"Exercise '{exercise_name}' already exists in ExerciseLibrary (skipping).")
        return False
    except Exception as e:
        _logger.error(f"Error adding exercise '{exercise_name}' to ExerciseLibrary: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()