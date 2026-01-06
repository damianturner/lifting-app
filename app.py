import streamlit as st
import os
from logic.init import setup_logging, init_db, SupabaseConnection, get_pg_connection, seed_base_data, _get_supabase_client_resource
from logic.view_plan_page import render_view_plan_page, render_sidebar_stats
from logic.edit_plan_page import render_edit_plan_page

# 1. SETUP & CONFIG
# Pulling from the nested structure recommended for st.connection
postgres_url = st.secrets.get("connections", {}).get("supabase", {}).get("db_url")

# Initialize Logger and Supabase Client
logger = setup_logging()

# Initialize Database Schema and Base Data (Once per app lifecycle)
if postgres_url:
    init_db(postgres_url, logger)
    pg_conn_for_base_seed = get_pg_connection(postgres_url)
    seed_base_data(pg_conn_for_base_seed, logger)
    pg_conn_for_base_seed.close()
else:
    logger.error("Database URL not found in secrets under [connections.supabase].")
    st.error("Database URL not configured. Please check your secrets.toml.")
    st.stop()

def sync_user_data(pg_conn, logger, user_id):
    """
    Copies base categories and exercises to the user's tables if they don't exist.
    """
    if user_id is None:
        logger.warning("Attempted to sync user data with a None user_id.")
        return

    sync_key = f"synced_user_data_{user_id}"
    if st.session_state.get(sync_key, False):
        return

    logger.info(f"Syncing base data for user {user_id}...")
    cur = pg_conn.cursor()

    try:
        # Sync Categories
        cur.execute("SELECT name FROM base_categories")
        base_categories = {row[0] for row in cur.fetchall()}
        
        cur.execute("SELECT name FROM categories WHERE user_id = %s", (user_id,))
        user_categories = {row[0] for row in cur.fetchall()}
        
        missing_categories = base_categories - user_categories
        if missing_categories:
            for cat_name in missing_categories:
                cur.execute("INSERT INTO categories (name, user_id) VALUES (%s, %s) ON CONFLICT (name, user_id) DO NOTHING", (cat_name, user_id))
            logger.info(f"Synced {len(missing_categories)} categories for user {user_id}.")

        # Sync Exercises
        cur.execute("SELECT name, default_notes FROM base_exercises")
        base_exercises = {row[0]: row[1] for row in cur.fetchall()}
        
        cur.execute("SELECT name FROM exerciselibrary WHERE user_id = %s", (user_id,))
        user_exercises = {row[0] for row in cur.fetchall()}

        missing_exercises = base_exercises.keys() - user_exercises
        if missing_exercises:
            for ex_name in missing_exercises:
                default_notes = base_exercises[ex_name]
                cur.execute("INSERT INTO exerciselibrary (name, default_notes, user_id) VALUES (%s, %s, %s) ON CONFLICT (name, user_id) DO NOTHING", (ex_name, default_notes, user_id))
            logger.info(f"Synced {len(missing_exercises)} exercises for user {user_id}.")

        # Sync Exercise-Category relationships
        cur.execute("""
            SELECT be.name, bc.name 
            FROM base_exercise_categories bec
            JOIN base_exercises be ON bec.exercise_id = be.id
            JOIN base_categories bc ON bec.category_id = bc.id
        """)
        base_exercise_cat_pairs = cur.fetchall()

        for ex_name, cat_name in base_exercise_cat_pairs:
            # Get user's exercise_id and category_id
            cur.execute("SELECT id FROM exerciselibrary WHERE name = %s AND user_id = %s", (ex_name, user_id))
            ex_id_res = cur.fetchone()
            cur.execute("SELECT id FROM categories WHERE name = %s AND user_id = %s", (cat_name, user_id))
            cat_id_res = cur.fetchone()

            if ex_id_res and cat_id_res:
                exercise_id = ex_id_res[0]
                category_id = cat_id_res[0]
                cur.execute("INSERT INTO exercisecategories (exercise_id, category_id, user_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                            (exercise_id, category_id, user_id))

        pg_conn.commit()
        st.session_state[sync_key] = True
        logger.info(f"Data sync complete for user {user_id}.")
        
    except Exception as e:
        logger.error(f"Error during user data sync: {e}")
        pg_conn.rollback()


def login_form():
    st.title("🔐 Workout Architect")
    
    tab1, tab2 = st.tabs(["Log In", "Sign Up"])
    
    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In", use_container_width=True):
            try:
                # Supabase handles the verification
                res = _get_supabase_client_resource().auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                st.success("Logged in!")
                st.rerun()
            except Exception as e:
                st.error("Invalid email or password.")

    with tab2:
        new_email = st.text_input("Email", key="sig_email")
        new_password = st.text_input("Password", type="password", key="sig_pass")
        st.caption("Password must be at least 6 characters.")
        if st.button("Create Account", use_container_width=True):
            try:
                _get_supabase_client_resource().auth.sign_up({"email": new_email, "password": new_password})
                st.info("Check your email for a confirmation link!")
            except Exception as e:
                st.error(f"Error: {e}")

@st.cache_data(ttl=3600) # Cache user data for 1 hour
def _get_current_user():
    try:
        _client = _get_supabase_client_resource()
        response = _client.auth.get_user()
        if response and response.user:
            return response.user
        return None
    except Exception as e:
        logger.debug(f"Error fetching current user: {e}")
        return None

def logout():
    _get_supabase_client_resource().auth.sign_out()
    if "user" in st.session_state:
        del st.session_state.user
    _get_current_user.clear() # Clear the cached user on logout
    st.rerun()

# Get current user (either from session state or by fetching)
current_user = None
if "user" in st.session_state:
    current_user = st.session_state.user
else:
    current_user = _get_current_user()
    if current_user:
        st.session_state.user = current_user

# Sync base data for the logged-in user
pg_conn = None
try:
    if current_user:
        user_id = current_user.id
        pg_conn = get_pg_connection(postgres_url)
        sync_user_data(pg_conn, logger, user_id)
    else:
        logger.info("No active session found. Skipping user-specific data sync.")
except Exception as e:
    logger.debug(f"User not logged in or sync skipped: {e}")
finally:
    if pg_conn:
        pg_conn.close()

# 2. SIDEBAR TOOLS (Logs & Stats)
def render_sidebar_tools():
    render_sidebar_stats()
    with st.sidebar:
        st.divider()
        st.subheader("🛠️ Internal Logs")
        log_text = st.session_state.log_buffer.getvalue()
        st.text_area("Debug Console", value=log_text, height=200, disabled=True)
        if st.button("Clear Logs"):
            st.session_state.log_buffer.truncate(0)
            st.session_state.log_buffer.seek(0)
            st.rerun()

render_sidebar_tools()

# If no user in session state (meaning not logged in and not found via cache)
if "user" not in st.session_state:
    login_form()
    st.stop() # Stop execution here so they don't see the app

# --- IF LOGGED IN, SHOW THE APP ---
st.sidebar.write(f"Logged in as: {st.session_state.user.email}")
if st.sidebar.button("Logout"):
    logout()


# 3. ROUTING LOGIC
if 'page' not in st.session_state:
    st.session_state.page = 'home'

if st.session_state.page == 'home':
    st.title("🏋️ Workout Architect")
    col1, col2 = st.columns(2)
    if col1.button("📂 View Plans", use_container_width=True):
        st.session_state.page = 'view_plan'
        st.rerun()
    if col2.button("🏗️ Create New Plan", use_container_width=True):
        st.session_state.page = 'edit_plan'
        st.rerun()

elif st.session_state.page == 'view_plan':
    render_view_plan_page(logger)

elif st.session_state.page == 'edit_plan':
    render_edit_plan_page(logger)