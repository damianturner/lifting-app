import streamlit as st
import sqlite3
import json
import logging

logger = logging.getLogger(__name__)

def render_edit_plan_page(db_path):
    st.title("🏗️ Macro Planner")

    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cur = conn.cursor()

    # --- 1. PRE-FETCH LIBRARY DATA ---
    try:
        query = """
            SELECT e.name, GROUP_CONCAT(c.name, ', ') 
            FROM ExerciseLibrary e
            LEFT JOIN ExerciseCategories ec ON e.id = ec.exercise_id
            LEFT JOIN Categories c ON ec.category_id = c.id
            GROUP BY e.id ORDER BY e.name
        """
        lib_raw = cur.execute(query).fetchall()
        lib_exercises = [f"{row[0]} [{row[1]}]" if row[1] else row[0] for row in lib_raw]
        lib_lookup = {f"{row[0]} [{row[1]}]" if row[1] else row[0]: row[0] for row in lib_raw}
        
        lib_schemes = {row[0]: (json.loads(row[1]), json.loads(row[2])) 
                       for row in cur.execute("SELECT name, reps_json, weight_json FROM RepSchemeLibrary").fetchall()}
    except Exception as e:
        logger.error(f"Lib fetch failed: {e}")
        lib_exercises, lib_lookup, lib_schemes = [], {}, {}

    # --- 2. GLOBAL SETTINGS ---
    col_a, col_b, col_c = st.columns([2, 1, 1])
    macro_name = col_a.text_input("Macro Name", "Block 1")
    num_minis = col_b.number_input("Weeks (Mini Cycles)", min_value=1, value=4)
    workouts_per_mini = col_c.number_input("Workouts/Week", min_value=1, value=3)

    if 'workout_templates' not in st.session_state:
        st.session_state.workout_templates = {}

    final_template_data = []

    # --- 3. THE HIERARCHY BUILDER ---
    for i in range(int(workouts_per_mini)):
        with st.expander(f"Workout {i+1} Details", expanded=True):
            w_name = st.text_input(f"Workout Name", value=f"Day {i+1}", key=f"wname_{i}")
            
            if i not in st.session_state.workout_templates:
                # Initialize with a list containing one exercise that has a list of sets
                st.session_state.workout_templates[i] = [
                    {"name": "", "sets": [{"reps": 10, "weight": 0.0}], "notes": ""}
                ]
            
            current_exercises = st.session_state.workout_templates[i]
            
            for ex_idx, ex in enumerate(current_exercises):
                with st.container(border=True):
                    h_cols = st.columns([2, 2, 1])
                    
                    # A. Quick Select Exercise
                    ex_choice = h_cols[0].selectbox("Exercise Search", ["-- Manual --"] + lib_exercises, key=f"lib_ex_{i}_{ex_idx}")
                    if ex_choice != "-- Manual --":
                        clean_name = lib_lookup[ex_choice]
                        if ex['name'] != clean_name:
                            ex['name'] = clean_name
                            st.session_state[f"ex_name_input_{i}_{ex_idx}"] = clean_name
                            st.rerun()

                    # B. Apply Rep Scheme (Bulk update sets)
                    scheme_choice = h_cols[1].selectbox("Rep Schemes", ["-- Custom --"] + list(lib_schemes.keys()), key=f"lib_sch_{i}_{ex_idx}")
                    if scheme_choice != "-- Custom --":
                        reps_list, weights_list = lib_schemes[scheme_choice]
                        # Convert library list into our set dictionary format
                        new_sets = [{"reps": r, "weight": w} for r, w in zip(reps_list, weights_list)]
                        if ex['sets'] != new_sets:
                            ex['sets'] = new_sets
                            st.rerun()
                    
                    if h_cols[2].button("🗑️ Remove", key=f"del_ex_{i}_{ex_idx}"):
                        st.session_state.workout_templates[i].pop(ex_idx)
                        st.rerun()

                    # ROW 2: Name and Global Set Count
                    m_cols = st.columns([3, 1])
                    ex['name'] = m_cols[0].text_input("Exercise Name", value=ex['name'], key=f"ex_name_input_{i}_{ex_idx}")
                    
                    # Adjust set count dynamically
                    num_sets = m_cols[1].number_input("Sets", 1, 20, value=len(ex['sets']), key=f"set_count_{i}_{ex_idx}")
                    if num_sets != len(ex['sets']):
                        if num_sets > len(ex['sets']):
                            # Append copies of the last set
                            last_val = ex['sets'][-1] if ex['sets'] else {"reps": 10, "weight": 0.0}
                            ex['sets'].extend([last_val.copy() for _ in range(num_sets - len(ex['sets']))])
                        else:
                            # Trim the list
                            ex['sets'] = ex['sets'][:num_sets]
                        st.rerun()

                    # ROW 3: INDIVIDUAL SET ROWS
                    st.write("Set Blueprint:")
                    for s_idx, set_data in enumerate(ex['sets']):
                        s_cols = st.columns([0.5, 2, 2])
                        s_cols[0].write(f"#{s_idx+1}")
                        set_data['reps'] = s_cols[1].number_input("Reps", 1, 100, value=int(set_data['reps']), key=f"r_{i}_{ex_idx}_{s_idx}")
                        set_data['weight'] = s_cols[2].number_input("Lbs", 0.0, 1000.0, value=float(set_data['weight']), key=f"w_{i}_{ex_idx}_{s_idx}")
                    
                    ex['notes'] = st.text_area("Notes", value=ex.get('notes', ""), key=f"note_{i}_{ex_idx}", height=70)
            
            if st.button(f"➕ Add Exercise", key=f"add_ex_{i}"):
                st.session_state.workout_templates[i].append({"name": "", "sets": [{"reps": 10, "weight": 0.0}], "notes": ""})
                st.rerun()
            
            final_template_data.append({"name": w_name, "exercises": current_exercises})

    # --- 4. DATABASE WRITE ---
    if st.button("🚀 Generate Blueprint", type="primary", use_container_width=True):
        try:
            cur.execute("INSERT INTO MacroCycles (name) VALUES (?)", (macro_name,))
            m_id = cur.lastrowid
            
            for m_idx in range(1, int(num_minis) + 1):
                cur.execute("INSERT INTO MiniCycles (macro_id, name) VALUES (?, ?)", (m_id, f"Week {m_idx}"))
                mini_id = cur.lastrowid
                
                for workout in final_template_data:
                    cur.execute("INSERT INTO Workouts (mini_id, name) VALUES (?, ?)", (mini_id, workout['name']))
                    w_id = cur.lastrowid
                    
                    for ex in workout['exercises']:
                        # Prepare the lists for JSON storage
                        reps_json = json.dumps([s['reps'] for s in ex['sets']])
                        weights_json = json.dumps([s['weight'] for s in ex['sets']])
                        
                        cur.execute("""
                            INSERT INTO ExerciseTemplates 
                            (workout_id, exercise_name, target_reps_json, target_weights_json, notes) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (w_id, ex['name'], reps_json, weights_json, ex['notes']))
            
            conn.commit()
            st.success("Variable set-plan generated!")
            st.balloons()
        except Exception as e:
            st.error(f"Save failed: {e}")
        finally:
            conn.close()