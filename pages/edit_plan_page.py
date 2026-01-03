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
    exercises: list[ExerciseTemplate] = field(default_factory=list)

# --- Callback Functions ---
def _apply_exercise_choice(workout_template_idx, exercise_idx, lookup):
    """Updates the exercise name in the ExerciseTemplate object when a library item is picked."""
    choice_key = f"lib_ex_{workout_template_idx}_{exercise_idx}"
    exercise_choice = st.session_state[choice_key]
    
    if exercise_choice == "(Select Exercise)":
        st.session_state.workout_templates[workout_template_idx].exercises[exercise_idx].name = "" # Set to empty if manual
        return

    selected_name = lookup[exercise_choice][0] # Access only the exercise name
    
    # Update the ExerciseTemplate object directly
    st.session_state.workout_templates[workout_template_idx].exercises[exercise_idx].name = selected_name

def render_add_exercise_form(db_path, parent_key):
    logger = setup_logging() # Ensure logger is set up here

    st.subheader("Add New Exercise to Library")
    
    # Fetch all existing categories for the multiselect
    form_conn = sqlite3.connect(db_path, check_same_thread=False) # Use a separate connection for the form
    form_cur = form_conn.cursor()
    all_categories = [row[0] for row in form_cur.execute("SELECT name FROM Categories ORDER BY name").fetchall()]
    form_conn.close() # Close connection after fetching

    with st.form(f"new_exercise_form_{parent_key}", clear_on_submit=True):
        new_exercise_name_input = st.text_input("Exercise Name (e.g., 'Incline Dumbbell Press')", key=f"new_exercise_name_form_{parent_key}")
        new_exercise_notes_input = st.text_area("Default Notes (optional)", key=f"new_exercise_notes_form_{parent_key}")
        selected_categories = st.multiselect(
            "Body Part / Type Tags (select existing or type new ones)",
            options=all_categories,
            default=[],
            key=f"new_exercise_categories_form_{parent_key}"
        )
        
        submitted = st.form_submit_button("Save New Exercise to Library")

        if submitted:
            if new_exercise_name_input:
                if insert_exercise_to_library(db_path, new_exercise_name_input, new_exercise_notes_input, selected_categories, _logger=logger):
                    st.success(f"Exercise '{new_exercise_name_input}' added to library with tags: {', '.join(selected_categories) if selected_categories else 'None'}")
                    st.rerun() # Rerun to display the form and close popover
                else:
                    st.error(f"Could not add '{new_exercise_name_input}'. It might already exist in the library.")
            else:
                st.warning("Please enter an exercise name.")
    
    if st.button("Cancel", key=f"cancel_add_exercise_form_{parent_key}"):
        st.rerun() # Rerun to close the popover and clear the form

def render_edit_plan_page(db_path):
    st.title("Macrocycle Planner")

    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()

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
        exercise_library_data = cur.execute(exercise_query).fetchall()
        # exercise_options will display "Exercise Name [Category, ...]"
        exercise_options = [f"{r[1]} [{r[2]}]" if r[2] else r[1] for r in exercise_library_data]
        # name_lookup will map "Exercise Name [Category, ...]" to (exercise_name, exercise_id)
        # It's important to update the name_lookup with the correct mapping if new exercises are added
        name_lookup = {f"{r[1]} [{r[2]}]" if r[2] else r[1]: (r[1], r[0]) for r in exercise_library_data}
        
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
                    h_cols = st.columns([2, 0.5, 0.5]) # Adjusted column widths
                    
                    # Determine the default index for the selectbox
                    current_exercise_name = exercise_template.name
                    default_index = 0
                    if current_exercise_name:
                        # Try to find the current exercise name in the display options
                        # (Exercise Name [Category, ...])
                        for i, option in enumerate(exercise_options):
                            # Extract just the name from the option to match current_exercise_name
                            if '[' in option:
                                option_name = option.split(' [')[0]
                            else:
                                option_name = option
                            
                            if option_name == current_exercise_name:
                                default_index = i + 1 # +1 because (Select Exercise)" is at index 0
                                break

                    h_cols[0].selectbox("Lift Name", ["(Select Exercise)"] + exercise_options,
                        key=f"lib_ex_{workout_template_index}_{exercise_index}",
                        on_change=_apply_exercise_choice,
                        args=(workout_template_index, exercise_index, name_lookup),
                        index=default_index)
                    
                    # Add new exercise button
                    with h_cols[1].popover("➕ Add New Exercise", use_container_width=True):
                        render_add_exercise_form(db_path, parent_key=f"add_new_ex_{workout_template_index}_{exercise_index}")

                    if h_cols[2].button("🗑️ Remove Lift", key=f"del_{workout_template_index}_{exercise_index}"):
                        workout_template.exercises.pop(exercise_index)
                        st.rerun()