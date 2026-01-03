import streamlit as st
import sqlite3
import json
import logging
from dataclasses import dataclass, field
from init import setup_logging, insert_exercise_to_library # Import the new function and setup_logging

logger = logging.getLogger(__name__)

# --- Dataclasses for structured state management ---

@dataclass
class ExerciseTemplate:
    name: str = ""
    sets: int = 3
    rirs: list[int] = field(default_factory=lambda: [2, 2, 2])
    notes: str = ""

@dataclass
class WorkoutTemplate:
    name: str = ""
    exercises: list[ExerciseTemplate] = field(default_factory=lambda: [ExerciseTemplate()])

# --- Callback Functions ---

def _apply_exercise_choice(workout_template_idx, exercise_idx, lookup):
    """Updates the exercise name in the ExerciseTemplate object when a library item is picked."""
    choice_key = f"lib_ex_{workout_template_idx}_{exercise_idx}"
    exercise_choice = st.session_state[choice_key]
    
    if exercise_choice == "-- Manual --":
        return

    selected_name = lookup[exercise_choice]
    
    # Update the ExerciseTemplate object directly
    st.session_state.workout_templates[workout_template_idx].exercises[exercise_idx].name = selected_name
    # Update the text input's session state key directly to reflect the change in UI
    st.session_state[f"ex_name_input_{workout_template_idx}_{exercise_idx}"] = selected_name


def render_edit_plan_page(db_path):
    st.title("Macrocycle Planner")

    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()
    
    # --- Add New Exercise Section ---
    with st.expander("➕ Add New Exercise to Library", expanded=False):
        # Use session state for input fields to allow clearing
        if "new_exercise_name" not in st.session_state:
            st.session_state.new_exercise_name = ""
        if "new_exercise_notes" not in st.session_state:
            st.session_state.new_exercise_notes = ""

        new_exercise_name_input = st.text_input("Exercise Name (e.g., 'Incline Dumbbell Press')", key="new_exercise_name")
        new_exercise_notes_input = st.text_area("Default Notes (optional)", key="new_exercise_notes")
        
        if st.button("Save New Exercise to Library"):
            if new_exercise_name_input:
                # Get the logger instance
                logger_for_init = setup_logging() 
                if insert_exercise_to_library(db_path, new_exercise_name_input, new_exercise_notes_input, _logger=logger_for_init):
                    st.success(f"Exercise '{new_exercise_name_input}' added to library!")
                    # Clear input fields after successful save
                    st.session_state.new_exercise_name = ""
                    st.session_state.new_exercise_notes = ""
                    st.rerun() # Rerun to update the exercise library dropdown
                else:
                    st.error(f"Could not add '{new_exercise_name_input}'. It might already exist in the library.")
            else:
                st.warning("Please enter an exercise name.")

    conn = sqlite3.connect(db_path, check_same_thread=False)
    cur = conn.cursor()

    # --- 1. LIBRARY DATA ---
    try:
        exercise_query = """
            SELECT e.id, e.name, GROUP_CONCAT(c.name, ', ')
            FROM ExerciseLibrary e
            LEFT JOIN ExerciseCategories ec ON e.id = ec.exercise_id
            LEFT JOIN Categories c ON ec.category_id = c.id
            GROUP BY e.id ORDER BY e.name
        """
        raw_lib = cur.execute(exercise_query).fetchall()
        # exercise_options will display "Exercise Name [Category, ...]"
        exercise_options = [f"{r[1]} [{r[2]}]" if r[2] else r[1] for r in raw_lib]
        # name_lookup will map "Exercise Name [Category, ...]" to (exercise_name, exercise_id)
        # It's important to update the name_lookup with the correct mapping if new exercises are added
        name_lookup = {f"{r[1]} [{r[2]}]" if r[2] else r[1]: (r[1], r[0]) for r in raw_lib}
        
    except Exception as e:
        exercise_options, name_lookup = [], {}

    # --- 2. GLOBAL SETTINGS ---
    st.subheader("Plan Settings")
    c1, c2, c3 = st.columns([2, 1, 1])
    macro_name = st.text_input("Macro Name", "New Plan (eg. Winter Bulk 26)")
    num_weeks = st.number_input("Weeks", 1, 52, 4)
    per_week = st.number_input("Workouts/Week", 1, 14, 3)


    # --- 3. BUILDER ---
    # Initialize workout_templates in session state if not already present
    if 'workout_templates' not in st.session_state:
        st.session_state.workout_templates = [WorkoutTemplate(name=f"Day {i+1}") for i in range(int(per_week))]
    
    # Adjust the number of workout templates if 'per_week' changes
    while len(st.session_state.workout_templates) < int(per_week):
        st.session_state.workout_templates.append(WorkoutTemplate(name=f"Day {len(st.session_state.workout_templates)+1}"))
    st.session_state.workout_templates = st.session_state.workout_templates[:int(per_week)]

    for workout_template_index, workout_template in enumerate(st.session_state.workout_templates):
        with st.expander(f"Workout Template {workout_template_index+1}: {workout_template.name}", expanded=True):
            workout_template.name = st.text_input("Workout Name", value=workout_template.name, key=f"wname_{workout_template_index}")
            
            # Use a copy to iterate to allow modification during iteration (e.g., pop)
            exercises_to_render = list(workout_template.exercises) 

            for exercise_index, exercise_template in enumerate(exercises_to_render):
                with st.container(border=True):
                    h_cols = st.columns([2, 1])
                    
                    h_cols[0].selectbox("Search Library", ["-- Manual --"] + exercise_options,
                        key=f"lib_ex_{workout_template_index}_{exercise_index}",
                        on_change=_apply_exercise_choice,
                        args=(workout_template_index, exercise_index, name_lookup))
                    
                    if h_cols[1].button("🗑️", key=f"del_{workout_template_index}_{exercise_index}"):
                        workout_template.exercises.pop(exercise_index)
                        st.rerun()

                    # --- Sync Inputs ---
                    exercise_template.name = st.text_input("Exercise Name", value=exercise_template.name, key=f"ex_name_input_{workout_template_index}_{exercise_index}")
                    
                    num_sets_key = f"set_count_{workout_template_index}_{exercise_index}"
                    num_sets_ui = st.number_input("Sets", 1, 20, value=exercise_template.sets, key=num_sets_key)
                    
                    # Resize RIR list if needed
                    if num_sets_ui != exercise_template.sets:
                        exercise_template.sets = num_sets_ui
                        # Keep existing RIRs, pad with default if growing
                        new_rirs = exercise_template.rirs[:num_sets_ui]
                        while len(new_rirs) < num_sets_ui:
                            new_rirs.append(2) # Default RIR
                        exercise_template.rirs = new_rirs
                        st.rerun() # Rerun to update RIR number inputs immediately

                    # --- Set-by-Set Rendering for RIR ---
                    st.write("Blueprint (RIR per Set):")
                    cols = st.columns(exercise_template.sets)
                    for set_index in range(exercise_template.sets):
                        rir_key = f"rir_{workout_template_index}_{exercise_index}_{set_index}"
                        
                        # Ensure rirs list is long enough for the current set_index
                        while len(exercise_template.rirs) <= set_index:
                            exercise_template.rirs.append(2) # Pad with default RIR
                        
                        exercise_template.rirs[set_index] = cols[set_index].number_input(
                            f"Set {set_index+1}", 0, 5, 
                            value=exercise_template.rirs[set_index],
                            key=rir_key,
                            label_visibility="visible"
                        )
                    
                    exercise_template.notes = st.text_area("Notes", value=exercise_template.notes, key=f"note_{workout_template_index}_{exercise_index}")

            if st.button(f"➕ Add Exercise to {workout_template.name}", key=f"add_{workout_template_index}"):
                workout_template.exercises.append(ExerciseTemplate())
                st.rerun()

    # --- 4. GENERATE ---
    st.divider()
    if st.button("🚀 Generate Blueprint", type="primary", use_container_width=True):
        try:
            # Check if all exercise names are available in the library
            missing_exercises = []
            for workout_template in st.session_state.workout_templates:
                for exercise_template in workout_template.exercises:
                    if exercise_template.name: # Only check if a name is provided
                        # Try to find the exercise in name_lookup, which now contains (name, id)
                        found = False
                        for display_name, (ex_name, ex_id) in name_lookup.items():
                            if ex_name == exercise_template.name:
                                exercise_template.library_id = ex_id # Temporarily store ID
                                found = True
                                break
                        if not found:
                            missing_exercises.append(exercise_template.name)
            
            if missing_exercises:
                st.error(f"Cannot save plan: The following exercises are not in the library or have empty names: {', '.join(set(missing_exercises))}. Please add them via an admin interface or select from the library.")
                conn.close()
                return

            cur.execute("INSERT INTO MacroCycles (name) VALUES (?)", (macro_name,))
            macro_cycle_id = cur.lastrowid
            
            for week_num in range(1, int(num_weeks) + 1):
                cur.execute("INSERT INTO MiniCycles (macro_id, name) VALUES (?, ?)", (macro_cycle_id, f"Week {week_num}"))
                mini_cycle_id = cur.lastrowid
                
                for workout_template_index, workout_template in enumerate(st.session_state.workout_templates):
                    cur.execute("INSERT INTO Workouts (mini_id, name) VALUES (?, ?)", (mini_cycle_id, workout_template.name))
                    workout_id = cur.lastrowid
                    
                    for exercise_template in workout_template.exercises:
                        # Retrieve exercise_library_id based on exercise_template.name
                        # This should be safe now because we pre-checked for missing exercises
                        if not hasattr(exercise_template, 'library_id'):
                            # Fallback if somehow library_id was not set (should not happen with pre-check)
                            lookup_result = cur.execute("SELECT id FROM ExerciseLibrary WHERE name = ?", (exercise_template.name,)).fetchone()
                            if lookup_result:
                                exercise_template.library_id = lookup_result[0]
                            else:
                                raise ValueError(f"Exercise '{exercise_template.name}' not found in library during final save.")
                        
                        cur.execute("INSERT INTO PlannedExercises (workout_id, exercise_library_id, sets, target_rir_json, notes) VALUES (?, ?, ?, ?, ?)",
                            (workout_id, exercise_template.library_id, exercise_template.sets, json.dumps(exercise_template.rirs), exercise_template.notes))
            conn.commit()
            st.success("Plan Saved!")
            
            # Clear relevant session state after saving to reset the form
            for key in list(st.session_state.keys()):
                if key.startswith('wname_') or key.startswith('lib_ex_') or key.startswith('ex_name_input_') or key.startswith('set_count_') or key.startswith('rir_') or key.startswith('note_'):
                    del st.session_state[key]
            # Ensure workout_templates is reset to its initial state based on per_week setting
            st.session_state.workout_templates = [WorkoutTemplate(name=f"Day {i+1}") for i in range(int(per_week))]
            st.rerun()

        except Exception as e:
            st.error(f"Failed to save plan: {e}")
            logger.error(f"Plan generation failed: {e}", exc_info=True)
        finally:
            conn.close()