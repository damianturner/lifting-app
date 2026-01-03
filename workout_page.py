import streamlit as st
import sqlite3
from datetime import datetime

def render_workout_page(db_path):
    st.title("🏋️ Active Session")

    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cur = conn.cursor()

    # 1. FIND THE NEXT WORKOUT (Clean Slate Logic)
    # We find the first workout that doesn't have a record in WorkoutLogs
    query = """
        SELECT w.id, w.name, m.name as week_name, mc.name as plan_name
        FROM Workouts w
        JOIN MiniCycles m ON w.mini_id = m.id
        JOIN MacroCycles mc ON m.macro_id = mc.id
        LEFT JOIN WorkoutLogs wl ON w.id = wl.workout_id
        WHERE wl.id IS NULL
        ORDER BY mc.id, m.id, w.id LIMIT 1
    """
    next_workout = cur.execute(query).fetchone()

    if not next_workout:
        st.success("🎉 All workouts in this plan are completed!")
        if st.button("Back to Home"):
            st.session_state.page = "home"
            st.rerun()
        return

    w_id, w_name, week_name, plan_name = next_workout
    st.caption(f"{plan_name} / {week_name}")
    st.subheader(f"Today's Session: {w_name}")

    # 2. LOAD SESSION BUFFER (If not already in memory)
    session_key = f"active_session_{w_id}"
    if session_key not in st.session_state:
        # Pull the blueprint for this workout
        templates = cur.execute("""
            SELECT id, exercise_name, target_sets, target_reps, target_weight, notes 
            FROM ExerciseTemplates WHERE workout_id = ?
        """, (w_id,)).fetchall()
        
        buffer = []
        for t in templates:
            # Create a dictionary for the exercise with a list of "Actual" set results
            buffer.append({
                "template_id": t[0],
                "name": t[1],
                "planned_sets": t[2],
                "planned_reps": t[3],
                "planned_weight": t[4],
                "notes": t[5],
                "actual_sets": [{"reps": t[3], "weight": t[4], "rpe": 7} for _ in range(t[2])]
            })
        st.session_state[session_key] = buffer

    # 3. UI RENDERING & ON-THE-FLY EDITS
    active_session = st.session_state[session_key]

    for ex_idx, ex in enumerate(active_session):
        with st.container(border=True):
            cols = st.columns([4, 1])
            cols[0].markdown(f"### {ex['name']}")
            if cols[1].button("🗑️", key=f"del_ex_{ex_idx}", help="Remove exercise from today's session"):
                active_session.pop(ex_idx)
                st.rerun()
            
            st.caption(f"🎯 Target: {ex['planned_sets']}x{ex['planned_reps']} @ {ex['planned_weight']} lbs")
            if ex['notes']:
                st.info(f"💡 {ex['notes']}")

            # Header for Sets
            h_cols = st.columns([1, 2, 2, 2, 1])
            h_cols[0].caption("Set")
            h_cols[1].caption("Weight")
            h_cols[2].caption("Reps")
            h_cols[3].caption("RPE")

            for s_idx, s_data in enumerate(ex['actual_sets']):
                s_cols = st.columns([1, 2, 2, 2, 1])
                s_cols[0].write(f"**{s_idx + 1}**")
                
                # Input boxes: default to planned values
                s_data['weight'] = s_cols[1].number_input("W", value=float(s_data['weight']), key=f"w_{w_id}_{ex_idx}_{s_idx}", label_visibility="collapsed")
                s_data['reps'] = s_cols[2].number_input("R", value=int(s_data['reps']), key=f"r_{w_id}_{ex_idx}_{s_idx}", label_visibility="collapsed")
                s_data['rpe'] = s_cols[3].slider("RPE", 1, 10, value=7, key=f"rpe_{w_id}_{ex_idx}_{s_idx}", label_visibility="collapsed")
                
                if s_cols[4].button("❌", key=f"del_s_{ex_idx}_{s_idx}"):
                    ex['actual_sets'].pop(s_idx)
                    st.rerun()

            if st.button(f"➕ Add Set to {ex['name']}", key=f"add_s_{ex_idx}"):
                # Add a set matching the last set's data
                last_set = ex['actual_sets'][-1].copy() if ex['actual_sets'] else {"reps": 10, "weight": 0, "rpe": 7}
                ex['actual_sets'].append(last_set)
                st.rerun()

    # ADD NEW EXERCISE ON THE FLY
    st.divider()
    with st.expander("➕ Add Extra Exercise (Not in Blueprint)"):
        # Fetch library for quick selection
        lib_exs = [r[0] for r in cur.execute("SELECT name FROM ExerciseLibrary").fetchall()]
        new_ex_name = st.selectbox("Search Library", ["-- Select --"] + lib_exs)
        if st.button("Add to Today's Session") and new_ex_name != "-- Select --":
            active_session.append({
                "template_id": None, # This was not planned
                "name": new_ex_name,
                "planned_sets": 0,
                "planned_reps": 0,
                "planned_weight": 0,
                "notes": "Added on the fly",
                "actual_sets": [{"reps": 10, "weight": 0, "rpe": 7}]
            })
            st.rerun()

    # 4. FINISH & SAVE
    if st.button("✅ Finish Workout", type="primary", use_container_width=True):
        # 1. Create the Log Entry
        cur.execute("INSERT INTO WorkoutLogs (workout_id) VALUES (?)", (w_id,))
        log_id = cur.lastrowid
        
        # 2. Save every set performed
        for ex in active_session:
            for s_idx, s_data in enumerate(ex['actual_sets']):
                cur.execute("""
                    INSERT INTO SetLogs (workout_log_id, exercise_template_id, exercise_name, set_number, weight, reps, rpe)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (log_id, ex['template_id'], ex['name'], s_idx + 1, s_data['weight'], s_data['reps'], s_data['rpe']))
        
        conn.commit()
        del st.session_state[session_key]
        st.success("Workout Saved to History!")
        st.balloons()
        if st.button("Back to Home"):
            st.session_state.page = "home"
            st.rerun()

    conn.close()