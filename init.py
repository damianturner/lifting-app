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
        seed_library(conn) # Seed immediately after schema
        _logger.info("Database and Seed Data initialized successfully.")
    except Exception as e:
        _logger.error(f"Database Init Failed: {e}", exc_info=True)
    finally:
        conn.close()

# --- 3. DB SEEDING LOGIC ---
@st.cache_resource
def seed_library(_conn):
    cur = _conn.cursor()
    exercise_library_map = {
        "Barbell Bench Press": ["Chest", "Shoulders", "Triceps"],
        "Pull Up": ["Back", "Biceps", "Forearms"],
        "Deadlift": ["Back", "Hamstrings", "Forearms"],
        "Barbell Back Squat": ["Quads", "Glutes", "Hamstrings"]
    }

    # Map: { Scheme Name: (Reps List, Weights/Intensity List) }
    schemes_map = {
        "5x5 Strength": ([5, 5, 5, 5, 5], [0, 0, 0, 0, 0]),
        "3x10 Hypertrophy": ([10, 10, 10], [0, 0, 0]),
        "4x8 Standard": ([8, 8, 8, 8], [0, 0, 0, 0]),
        "3x12 Accessory": ([12, 12, 12], [0, 0, 0]),
        "Pyramid (10-8-6)": ([10, 8, 6], [0, 0, 0])
    }

    all_cats = set(cat for cats in exercise_library_map.values() for cat in cats)
    for cat in all_cats:
        cur.execute("INSERT OR IGNORE INTO Categories (name) VALUES (?)", (cat,))

    for ex_name, cats in exercise_library_map.items():
        cur.execute("INSERT OR IGNORE INTO ExerciseLibrary (name, default_notes) VALUES (?, '')", (ex_name,))
        for cat in cats:
            cur.execute("""
                INSERT OR IGNORE INTO ExerciseCategories (exercise_id, category_id)
                VALUES (
                    (SELECT id FROM ExerciseLibrary WHERE name = ?),
                    (SELECT id FROM Categories WHERE name = ?)
                )
            """, (ex_name, cat))

    for scheme_name, (reps, weights) in schemes_map.items():
        cur.execute("""
            INSERT OR IGNORE INTO RepSchemeLibrary (name, reps_json, weight_json)
            VALUES (?, ?, ?)
        """, (scheme_name, json.dumps(reps), json.dumps(weights)))

    _conn.commit()