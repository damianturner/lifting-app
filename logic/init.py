import streamlit as st
from streamlit.connections import BaseConnection
import logging
import io
import sys
import os
import psycopg2
from supabase import create_client, Client



# --- 1. LOGGING SETUP ---
def setup_logging():
    if "log_buffer" not in st.session_state:
        st.session_state.log_buffer = io.StringIO()

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers():
        logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(stdout_handler)

    buffer_handler = logging.StreamHandler(st.session_state.log_buffer)
    buffer_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(buffer_handler)
    return logger

# --- 2. SUPABASE CONNECTION CLASS ---
class SupabaseConnection(BaseConnection[Client]):
    """Custom Streamlit Connection for Supabase Client"""
    
    def _connect(self, **kwargs) -> Client:
        # Prioritize secrets.toml [connections.supabase] structure
        if "url" in self._secrets:
            supabase_url = self._secrets["url"]
            supabase_key = self._secrets["key"]
        else:
            # Fallback to direct secrets or env vars
            supabase_url = kwargs.get("supabase_url") or st.secrets.get("SUPABASE_URL")
            supabase_key = kwargs.get("supabase_key") or st.secrets.get("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            raise Exception("Missing SUPABASE_URL or SUPABASE_KEY.")
            
        return create_client(supabase_url, supabase_key)

    @property
    def client(self) -> Client:
        return self._instance

@st.cache_resource
def _get_supabase_client_resource() -> Client:
    """
    Returns a cached Supabase client instance using Streamlit's connection.
    This ensures the client is initialized once per session and reused.
    """
    conn = st.connection("supabase", type=SupabaseConnection)
    return conn.client

# --- 3. DATABASE INITIALIZATION ---
@st.cache_resource
def init_db(db_url, _logger):
    conn = None
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        if not os.path.exists('schema/schema.sql'):
            _logger.warning("schema.sql not found.")
            return

        with open('schema/schema.sql', 'r', encoding='utf-8-sig', errors='replace') as f:
            schema_sql = f.read()
        
        # PostgreSQL allows multi-statement execution in one call
        cur.execute(schema_sql)
        conn.commit()
        _logger.info("Database schema initialized successfully.")
        
    except Exception as e:
        _logger.error(f"Database Init Failed: {e}")
        st.error(f"Database initialization failed: {e}")
        st.stop()
    finally:
        if conn:
            conn.close()

# --- 4. DATA INSERTION HELPERS ---
def get_pg_connection(db_url):
    return psycopg2.connect(db_url)

def seed_base_data(_conn, _logger):
    seed_key = "seeded_base_data"
    if st.session_state.get(seed_key, False):
        return

    _logger.info("Seeding base data...")
    cur = _conn.cursor()

    common_categories = ["Chest", "Back", "Shoulders", "Biceps", "Triceps", "Quads", "Hamstrings", "Glutes", "Calves", "Core", "Forearms", "Full Body", "Upper Body", "Lower Body", "Push", "Pull", "Legs", "Compound", "Isolation"]
    for cat in common_categories:
        try:
            cur.execute("INSERT INTO base_categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (cat,))
        except Exception as e:
            _logger.warning(f"Failed to seed base category '{cat}': {e}")
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
        insert_base_exercise_to_library(_conn, ex_name, data["notes"], data["categories"], _logger=_logger)
    
    _conn.commit()
    st.session_state[seed_key] = True
    _logger.info("Base data seeding complete.")

def insert_base_exercise_to_library(_conn, exercise_name, default_notes="", category_names=None, _logger=None):
    if _logger is None: _logger = logging.getLogger()
    if category_names is None: category_names = []

    try:
        cur = _conn.cursor()
        cur.execute("INSERT INTO base_exercises (name, default_notes) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING RETURNING id",
                    (exercise_name, default_notes))
        
        res = cur.fetchone()
        if res:
            exercise_id = res[0]
        else:
            cur.execute("SELECT id FROM base_exercises WHERE name = %s", (exercise_name,))
            exercise_id = cur.fetchone()[0]

        for cat_name in category_names:
            cat_name = cat_name.strip()
            cur.execute("INSERT INTO base_categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING id", (cat_name,))
            cat_res = cur.fetchone()
            category_id = cat_res[0] if cat_res else None
            
            if not category_id:
                cur.execute("SELECT id FROM base_categories WHERE name = %s", (cat_name,))
                category_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO base_exercise_categories (exercise_id, category_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (exercise_id, category_id))

        return True
    except Exception as e:
        _logger.error(f"Error adding base exercise '{exercise_name}': {e}")
        return False