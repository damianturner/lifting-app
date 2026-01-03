import streamlit as st
import sqlite3
import logging
import json  # Added to parse JSON strings

logger = logging.getLogger(__name__)

def render_view_plan_page(db_path):
    st.title("📂 Your Macro Plans")
    
    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()

    conn = sqlite3.connect(db_path, check_same_thread=False)
    cur = conn.cursor()
    
    try:
        macros = cur.execute("SELECT id, name FROM MacroCycles").fetchall()
    except sqlite3.OperationalError:
        st.error("Database table not found. Please ensure schema is updated.")
        conn.close()
        return
    
    if not macros:
        st.warning("No plans found in the database.")
        conn.close()
        return

    macro_options = {name: id for id, name in macros}
    selected_macro_name = st.selectbox("Select a Plan", options=list(macro_options.keys()))
    macro_id = macro_options[selected_macro_name]

    minis = cur.execute(
        "SELECT id, name FROM MiniCycles WHERE macro_id = ?", (macro_id,)
    ).fetchall()

    if minis:
        tabs = st.tabs([m[1] for m in minis])
        
        for tab, (mini_id, mini_name) in zip(tabs, minis):
            with tab:
                workouts = cur.execute(
                    "SELECT id, name FROM Workouts WHERE mini_id = ?", (mini_id,)
                ).fetchall()
                
                if not workouts:
                    st.write("No workouts scheduled for this week.")

                for w_id, w_name in workouts:
                    with st.expander(f"🏋️ {w_name}", expanded=True):
                        # UPDATED QUERY: Reflecting JSON column names
                        query = """
                            SELECT 
                                t.exercise_name, 
                                t.target_reps_json, 
                                t.target_weights_json, 
                                t.notes,
                                (SELECT GROUP_CONCAT(c.name, ', ') 
                                 FROM Categories c
                                 JOIN ExerciseCategories ec ON c.id = ec.category_id
                                 JOIN ExerciseLibrary el ON ec.exercise_id = el.id
                                 WHERE el.name = t.exercise_name) as body_parts
                            FROM ExerciseTemplates t
                            WHERE t.workout_id = ?
                        """
                        exercises = cur.execute(query, (w_id,)).fetchall()
                        
                        if exercises:
                            # UPDATED TABLE HEADER
                            md_table = "| Exercise | Body Part | Sets | Reps (by set) | Weight (lbs) | Notes |\n"
                            md_table += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                            
                            for name, reps_json, weights_json, notes, body_parts in exercises:
                                try:
                                    # Parse the JSON lists
                                    reps_list = json.loads(reps_json) if reps_json else []
                                    weights_list = json.loads(weights_json) if weights_json else []
                                    
                                    sets_count = len(reps_list)
                                    # Join with "/" for a clean visual representation
                                    reps_display = " / ".join(map(str, reps_list))
                                    weights_display = " / ".join(map(str, weights_list))
                                    
                                    safe_notes = str(notes).replace("\n", " ") if notes else ""
                                    safe_parts = f"`{body_parts}`" if body_parts else "—"
                                    
                                    md_table += f"| **{name}** | {safe_parts} | {sets_count} | {reps_display} | {weights_display} | {safe_notes} |\n"
                                except json.JSONDecodeError:
                                    md_table += f"| **{name}** | Error | Error | Data Corruption | Check DB | |\n"
                            
                            st.markdown(md_table)
                        else:
                            st.info("No exercises added to this workout blueprint.")

    # --- DANGER ZONE ---
    st.divider()
    with st.expander("⚠️ Danger Zone"):
        st.write(f"Permanently delete the plan: **{selected_macro_name}**")
        if st.button(f"Confirm Delete {selected_macro_name}", type="primary"):
            try:
                cur.execute("DELETE FROM ExerciseTemplates WHERE workout_id IN (SELECT id FROM Workouts WHERE mini_id IN (SELECT id FROM MiniCycles WHERE macro_id = ?))", (macro_id,))
                cur.execute("DELETE FROM Workouts WHERE mini_id IN (SELECT id FROM MiniCycles WHERE macro_id = ?)", (macro_id,))
                cur.execute("DELETE FROM MiniCycles WHERE macro_id = ?", (macro_id,))
                cur.execute("DELETE FROM MacroCycles WHERE id = ?", (macro_id,))
                conn.commit()
                st.success("Plan deleted successfully!")
                st.rerun()
            except Exception as e:
                logger.error(f"Delete failed: {e}")
                st.error("Could not delete plan.")

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