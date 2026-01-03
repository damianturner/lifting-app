import streamlit as st
import sqlite3
import logging
import json  # Added to parse JSON strings

logger = logging.getLogger(__name__)

def _get_db_connection(db_path):
    """Establishes and returns a SQLite database connection."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    return conn

def _fetch_macro_cycles(cursor):
    """Fetches all macro cycles from the database."""
    try:
        macro_cycles = cursor.execute("SELECT id, name FROM MacroCycles").fetchall()
        return macro_cycles
    except sqlite3.OperationalError:
        st.error("Database table 'MacroCycles' not found. Please ensure schema is updated.")
        return []

def _select_macro_plan(macro_cycles):
    """Handles Streamlit selectbox for macro plans and returns selected macro details."""
    
    # Dictionary to store counts of each macro cycle name
    name_counts = {}
    for mc in macro_cycles:
        name_counts[mc["name"]] = name_counts.get(mc["name"], 0) + 1

    macro_display_options = []
    macro_display_to_id = {}

    for macro_cycle in macro_cycles:
        name = macro_cycle["name"]
        macro_id = macro_cycle["id"]
        
        display_name = name
        # If there are duplicates, append ID to make it unique for display
        if name_counts[name] > 1:
            display_name = f"{name} (ID: {macro_id})"
        
        macro_display_options.append(display_name)
        macro_display_to_id[display_name] = macro_id

    # Ensure there's a selected option if macro_display_options is not empty
    if macro_display_options:
        selected_display_name = st.selectbox("Select a Plan", options=macro_display_options)
        macro_id = macro_display_to_id[selected_display_name]
        
        # Find the original selected macro name for rendering (e.g., danger zone)
        original_selected_macro_name = next((mc['name'] for mc in macro_cycles if mc['id'] == macro_id), selected_display_name)
    else:
        # This case should ideally be handled before calling this function
        # but as a fallback, ensure default values for safety.
        selected_display_name = None
        macro_id = None
        original_selected_macro_name = None # Set original_selected_macro_name to None if no plans

    return original_selected_macro_name, macro_id

def _fetch_mini_cycles_for_macro(cursor, macro_id):
    """Fetches mini cycles for a given macro ID."""
    return cursor.execute(
        "SELECT id, name FROM MiniCycles WHERE macro_id = ?", (macro_id,)
    ).fetchall()

def _fetch_workouts_for_mini(cursor, mini_id):
    """Fetches workouts for a given mini ID."""
    return cursor.execute(
        "SELECT id, name FROM Workouts WHERE mini_id = ?", (mini_id,)
    ).fetchall()

def _fetch_planned_exercises_for_workout(cursor, workout_id):
    """Fetches planned exercises for a given workout ID."""
    # This complex query fetches all planned exercises for a given workout.
    # It joins with the ExerciseLibrary to get the canonical exercise name
    # and then performs a subquery to aggregate the names of all associated
    # body part categories for each exercise.
    query = """
        SELECT 
            el.name AS exercise_name,
            pe.sets, 
            pe.target_rir_json, 
            pe.notes,
            (SELECT GROUP_CONCAT(c.name, ', ') 
             FROM Categories c
             JOIN ExerciseCategories ec ON c.id = ec.category_id
             WHERE ec.exercise_id = pe.exercise_library_id) as body_parts
        FROM PlannedExercises pe
        JOIN ExerciseLibrary el ON pe.exercise_library_id = el.id
        WHERE pe.workout_id = ?
    """
    return cursor.execute(query, (workout_id,)).fetchall()

def _render_exercises_table(planned_exercises):
    """Renders a markdown table for the given planned exercises."""
    if planned_exercises:
        md_table = "| Exercise | Body Part | Sets | Target RIR (per set) | Notes |\n"
        md_table += "| :--- | :--- | :--- | :--- | :--- |\n"
        
        for planned_exercise in planned_exercises:
            try:
                rir_list = json.loads(planned_exercise["target_rir_json"]) if planned_exercise["target_rir_json"] else []
                rir_display = " / ".join(map(str, rir_list))
                
                safe_notes = str(planned_exercise["notes"]).replace("\n", " ") if planned_exercise["notes"] else ""
                safe_parts = f"`{planned_exercise['body_parts']}`" if planned_exercise["body_parts"] else "—"
                
                md_table += f"| **{planned_exercise['exercise_name']}** | {safe_parts} | {planned_exercise['sets']} | {rir_display} | {safe_notes} |\n"
            except json.JSONDecodeError:
                md_table += f"| **{planned_exercise['exercise_name']}** | Error | Data Corruption | Check DB | |\n"
        
        st.markdown(md_table)
    else:
        st.info("No exercises added to this workout blueprint.")

def _render_danger_zone(cursor, selected_macro_name, macro_id):
    """Renders the danger zone section for plan deletion."""
    st.divider()
    with st.expander("⚠️ Danger Zone"):
        st.write(f"Permanently delete the plan: **{selected_macro_name}**")
        if st.button(f"Confirm Delete {selected_macro_name}", type="primary"):
            try:
                # The ON DELETE CASCADE in the schema should handle most of this,
                # but explicit deletion ensures all related records are removed
                # if FK constraints are not perfectly cascading across all levels.
                cursor.execute("DELETE FROM PlannedExercises WHERE workout_id IN (SELECT id FROM Workouts WHERE mini_id IN (SELECT id FROM MiniCycles WHERE macro_id = ?))", (macro_id,))
                cursor.execute("DELETE FROM Workouts WHERE mini_id IN (SELECT id FROM MiniCycles WHERE macro_id = ?)", (macro_id,))
                cursor.execute("DELETE FROM MiniCycles WHERE macro_id = ?", (macro_id,))
                cursor.execute("DELETE FROM MacroCycles WHERE id = ?", (macro_id,))
                cursor.connection.commit()
                st.success("Plan deleted successfully!")
                st.rerun()
            except Exception as e:
                logger.error(f"Delete failed: {e}")
                st.error("Could not delete plan.")

def render_view_plan_page(db_path):
    st.title("Planned Macrocycles")
    
    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()

    conn = _get_db_connection(db_path)
    cur = conn.cursor()
    
    macro_cycles = _fetch_macro_cycles(cur)
    
    if not macro_cycles:
        st.warning("No plans found in the database.")
        conn.close()
        return

    selected_macro_name, macro_id = _select_macro_plan(macro_cycles)

    mini_cycles = _fetch_mini_cycles_for_macro(cur, macro_id)

    if mini_cycles:
        tabs = st.tabs([mini_cycle["name"] for mini_cycle in mini_cycles])
        
        for tab, mini_cycle in zip(tabs, mini_cycles):
            with tab:
                workouts = _fetch_workouts_for_mini(cur, mini_cycle["id"])
                
                if not workouts:
                    st.write("No workouts scheduled for this week.")

                for workout in workouts:
                    workout_id = workout["id"]
                    workout_name = workout["name"]
                    with st.expander(f"🏋️ {workout_name}", expanded=True):
                        planned_exercises = _fetch_planned_exercises_for_workout(cur, workout_id)
                        _render_exercises_table(planned_exercises)
    
    _render_danger_zone(cur, selected_macro_name, macro_id)

    conn.close()

def render_sidebar_stats(db_path):
    with st.sidebar:
        st.subheader("Database Stats")
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            count = cur.execute("SELECT COUNT(*) FROM MacroCycles").fetchone()[0]
            st.metric("Total Plans Saved", count)
            conn.close()
        except:
            st.sidebar.error("Stats unavailable")