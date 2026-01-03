import streamlit as st
import sqlite3
import json
import logging

logger = logging.getLogger(__name__)

# --- Callback Functions ---

def _apply_exercise_choice(w_idx, ex_idx, lookup):
    """Updates the exercise name input field when a library item is picked."""
    choice_key = f"lib_ex_{w_idx}_{ex_idx}"
    exercise_choice = st.session_state[choice_key]
    
    if exercise_choice == "-- Manual --":
        return

    selected_name = lookup[exercise_choice]
    # Update the text input's session state key directly
    st.session_state[f"ex_name_input_{w_idx}_{ex_idx}"] = selected_name
    # Update the underlying data structure
    st.session_state.workout_templates[w_idx][ex_idx]['name'] = selected_name

def _apply_rep_scheme(w_idx, ex_idx, schemes):
    """Nukes old widget states and forces new reps/weights from library."""
    scheme_key = f"lib_sch_{w_idx}_{ex_idx}"
    scheme_choice = st.session_state[scheme_key]

    if scheme_choice == "-- Custom --":
        return

    reps_list, weights_list = schemes[scheme_choice]
    exercise_details = st.session_state.workout_templates[w_idx][ex_idx]
    
    # 1. Clear out any existing set widget states to force a refresh
    for i in range(20): # Max sets safety buffer
        st.session_state.pop(f"r_{w_idx}_{ex_idx}_{i}", None)
        st.session_state.pop(f"w_{w_idx}_{ex_idx}_{i}", None)

    # 2. Update the underlying data
    new_sets = [{"reps": {"type": "reps", "value": r}, "weight": w} for r, w in zip(reps_list, weights_list)]
    exercise_details['sets'] = new_sets
    
    # 3. Update the 'Sets' number input widget state
    st.session_state[f"set_count_{w_idx}_{ex_idx}"] = len(new_sets)

def render_edit_plan_page(db_path):
    st.title("🏗️ Macro Planner")

    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cur = conn.cursor()

    # --- 1. LIBRARY DATA ---
    try:
        exercise_query = """
            SELECT e.name, GROUP_CONCAT(c.name, ', ')
            FROM ExerciseLibrary e
            LEFT JOIN ExerciseCategories ec ON e.id = ec.exercise_id
            LEFT JOIN Categories c ON ec.category_id = c.id
            GROUP BY e.id ORDER BY e.name
        """
        raw_lib = cur.execute(exercise_query).fetchall()
        exercise_options = [f"{r[0]} [{r[1]}]" if r[1] else r[0] for r in raw_lib]
        name_lookup = {f"{r[0]} [{r[1]}]" if r[1] else r[0]: r[0] for r in raw_lib}
        
        schemes = {r[0]: (json.loads(r[1]), json.loads(r[2]))
                   for r in cur.execute("SELECT name, reps_json, weight_json FROM RepSchemeLibrary").fetchall()}
    except Exception as e:
        exercise_options, name_lookup, schemes = [], {}, {}

    # --- 2. GLOBAL SETTINGS ---
    st.subheader("Plan Settings")
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    macro_name = c1.text_input("Macro Name", "New Plan")
    num_weeks = c2.number_input("Weeks", 1, 12, 4)
    per_week = c3.number_input("Workouts/Week", 1, 7, 3)
    with c4:
        st.write(" ") # Spacer for alignment
        st.checkbox("Set Weights", value=True, key="plan_has_weights")

    # --- 3. BUILDER ---
    if 'workout_templates' not in st.session_state:
        st.session_state.workout_templates = {}

    for w_idx in range(int(per_week)):
        with st.expander(f"Workout Template {w_idx+1}", expanded=True):
            st.text_input("Workout Name", value=f"Day {w_idx+1}", key=f"wname_{w_idx}")
            
            if w_idx not in st.session_state.workout_templates:
                st.session_state.workout_templates[w_idx] = [{"name": "", "sets": [{"reps": {"type": "reps", "value": 10}, "weight": 0.0}], "notes": ""}]
                st.session_state[f"set_count_{w_idx}_0"] = 1

            for ex_idx, ex_ref in enumerate(st.session_state.workout_templates[w_idx]):
                with st.container(border=True):
                    h_cols = st.columns([2, 2, 1])
                    
                    h_cols[0].selectbox("Search Library", ["-- Manual --"] + exercise_options,
                        key=f"lib_ex_{w_idx}_{ex_idx}",
                        on_change=_apply_exercise_choice,
                        args=(w_idx, ex_idx, name_lookup))

                    h_cols[1].selectbox("Apply Scheme", ["-- Custom --"] + list(schemes.keys()),
                        key=f"lib_sch_{w_idx}_{ex_idx}",
                        on_change=_apply_rep_scheme,
                        args=(w_idx, ex_idx, schemes))
                    
                    if h_cols[2].button("🗑️", key=f"del_{w_idx}_{ex_idx}"):
                        st.session_state.workout_templates[w_idx].pop(ex_idx)
                        st.rerun()

                    # --- Sync Inputs ---
                    # We use the key itself as the source of truth for the 'name'
                    name_key = f"ex_name_input_{w_idx}_{ex_idx}"
                    ex_ref['name'] = st.text_input("Exercise Name", key=name_key)
                    
                    num_sets = st.number_input("Sets", 1, 20, key=f"set_count_{w_idx}_{ex_idx}")
                    
                    # Resize set list if needed
                    if num_sets != len(ex_ref['sets']):
                        while len(ex_ref['sets']) < num_sets:
                            ex_ref['sets'].append({"reps": {"type": "reps", "value": 10}, "weight": 0.0})
                        ex_ref['sets'] = ex_ref['sets'][:num_sets]
                        st.rerun()

                    # --- Set-by-Set Rendering ---
                    st.write("Blueprint:")
                    for s_idx, s_ref in enumerate(ex_ref['sets']):
                        with st.container():
                            # --- Data Normalization & Key Setup ---
                            if not isinstance(s_ref.get('reps'), dict):
                                s_ref['reps'] = {"type": "reps", "value": s_ref.get('reps', 10)}

                            r_type_key = f"r_type_{w_idx}_{ex_idx}_{s_idx}"
                            r_val_key = f"r_val_{w_idx}_{ex_idx}_{s_idx}"
                            w_key = f"w_{w_idx}_{ex_idx}_{s_idx}"

                            # Initialize widget states from the canonical data source (s_ref)
                            if r_type_key not in st.session_state: st.session_state[r_type_key] = s_ref['reps']['type'].capitalize()
                            if r_val_key not in st.session_state: st.session_state[r_val_key] = int(s_ref['reps']['value'])
                            if w_key not in st.session_state: st.session_state[w_key] = float(s_ref['weight'])

                            # --- UI Layout ---
                            has_weights = st.session_state.get("plan_has_weights", True)
                            cols = st.columns([2, 1, 2]) if has_weights else st.columns([2, 1])
                            
                            # --- Reps/RIR Input ---
                            target_type = cols[0].radio(
                                f"S{s_idx+1} Target", ["Reps", "RIR"],
                                key=r_type_key,
                                horizontal=True
                            )
                            target_value = cols[1].number_input("Value", 1, 100, key=r_val_key, label_visibility="collapsed")
                            
                            # Update underlying data from UI widgets
                            s_ref['reps'] = {"type": target_type.lower(), "value": target_value}

                            # --- Weight Input ---
                            if has_weights:
                                weight_val = cols[2].number_input(
                                    "Lbs", 0.0, 1000.0,
                                    value=float(s_ref['weight']) if float(s_ref['weight']) > 0 else None,
                                    key=w_key,
                                    label_visibility="collapsed"
                                )
                                s_ref['weight'] = weight_val if weight_val is not None else 0.0
                            else:
                                s_ref['weight'] = 0.0
                    
                    ex_ref['notes'] = st.text_area("Notes", key=f"note_{w_idx}_{ex_idx}")

            if st.button(f"➕ Add Exercise", key=f"add_{w_idx}"):
                st.session_state.workout_templates[w_idx].append({"name": "", "sets": [{"reps": {"type": "reps", "value": 10}, "weight": 0.0}], "notes": ""})
                st.rerun()

    # --- 4. GENERATE ---
    st.divider()
    if st.button("🚀 Generate Blueprint", type="primary", use_container_width=True):
        try:
            cur.execute("INSERT INTO MacroCycles (name) VALUES (?)", (macro_name,))
            m_id = cur.lastrowid
            for w_num in range(1, int(num_weeks) + 1):
                cur.execute("INSERT INTO MiniCycles (macro_id, name) VALUES (?, ?)", (m_id, f"Week {w_num}"))
                mini_id = cur.lastrowid
                for w_temp in st.session_state.workout_templates.values():
                    cur.execute("INSERT INTO Workouts (mini_id, name) VALUES (?, ?)", (mini_id, "Workout"))
                    work_id = cur.lastrowid
                    for ex in w_temp:
                        cur.execute("INSERT INTO ExerciseTemplates VALUES (NULL, ?, ?, ?, ?, ?)",
                            (work_id, ex['name'], json.dumps([s['reps'] for s in ex['sets']]), 
                             json.dumps([s['weight'] for s in ex['sets']]), ex['notes']))
            conn.commit()
            st.success("Plan Saved!")
        finally:
            conn.close()