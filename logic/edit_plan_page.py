from logic.view_plan_page import _fetch_full_macro_cycle_details, _fetch_macro_cycles, render_sidebar_stats
from logic.init import _get_supabase_client_resource # Import the cached resource client
import streamlit as st
import json
import logging
from dataclasses import dataclass, field

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
        st.session_state.workout_templates[workout_template_idx].exercises[
            exercise_idx
        ].name = ""  # Set to empty if manual
        return

    selected_name = lookup[exercise_choice][0]  # Access only the exercise name

    # Update the ExerciseTemplate object directly
    st.session_state.workout_templates[workout_template_idx].exercises[
        exercise_idx
    ].name = selected_name



@st.cache_data(ttl=3600) # Cache for 1 hour
def _get_all_categories():
    """Fetches all category names from the database."""
    supabase_client = _get_supabase_client_resource()
    logger = logging.getLogger(__name__)
    try:
        response = supabase_client.table("categories").select("name").order("name").execute()
        return [row["name"] for row in response.data] if response.data else []
    except Exception as e:
        logger.error(f"Error fetching categories from Supabase: {e}", exc_info=True)
        return []

@st.cache_data(ttl=3600) # Cache for 1 hour
def _get_exercise_library_data():
    """Fetches all exercise library data with their categories."""
    supabase_client = _get_supabase_client_resource()
    logger = logging.getLogger(__name__)
    try:
        response = (
            supabase_client.table("exerciselibrary")
            .select("id, name, exercise_categories:exercisecategories(category:categories(name))")
            .order("name")
            .execute()
        )

        exercise_library_data = []
        if response.data:
            for ex in response.data:
                category_names = []
                if ex["exercise_categories"]:
                    for ec in ex["exercise_categories"]:
                        if ec["category"]:
                            category_names.append(ec["category"]["name"])

                exercise_library_data.append(
                    (ex["id"], ex["name"], ", ".join(category_names) if category_names else None)
                )
        return exercise_library_data
    except Exception as e:
        logger.error(f"Error fetching exercise library data from Supabase: {e}", exc_info=True)
        return []

def render_add_exercise_form(logger, parent_key):
    st.subheader("Add New Exercise to Library")

    all_categories = _get_all_categories()
    
    with st.form(f"new_exercise_form_{parent_key}", clear_on_submit=True):
        new_exercise_name_input = st.text_input(
            "Exercise Name (e.g., 'Incline Dumbbell Press')",
            key=f"new_exercise_name_form_{parent_key}",
        )
        new_exercise_notes_input = st.text_area(
            "Default Notes (optional)", key=f"new_exercise_notes_form_{parent_key}"
        )
        selected_categories = st.multiselect(
            "Body Part / Type Tags (select existing or type new ones)",
            options=all_categories,
            default=[],
            key=f"new_exercise_categories_form_{parent_key}",
        )

        submitted = st.form_submit_button("Save New Exercise to Library")

        if submitted:
            if new_exercise_name_input:
                try:
                    # Insert into ExerciseLibrary
                    # RLS handles user_id, so we don't pass it explicitly here
                    response = (
                        _get_supabase_client_resource.table("exerciselibrary")
                        .insert(
                            {
                                "name": new_exercise_name_input,
                                "default_notes": new_exercise_notes_input,
                            }
                        )
                        .execute()
                    )

                    if response.data:
                        exercise_id = response.data[0]["id"]

                        # Handle categories
                        for cat_name in selected_categories:
                            # Try to get existing category or insert new one
                            cat_response = (
                                _get_supabase_client_resource().table("categories")
                                .select("id")
                                .eq("name", cat_name)
                                .execute()
                            )
                            category_id = None
                            if cat_response.data:
                                category_id = cat_response.data[0]["id"]
                            else:
                                # If category doesn't exist for the current user, insert it
                                insert_cat_response = (
                                    _get_supabase_client_resource().table("categories")
                                    .insert({"name": cat_name})
                                    .execute()
                                )
                                if insert_cat_response.data:
                                    category_id = insert_cat_response.data[0]["id"]
                                    _get_all_categories.clear() # Clear cache if new category inserted


                            if category_id:
                                _get_supabase_client_resource().table("exercisecategories").insert(
                                    {
                                        "exercise_id": exercise_id,
                                        "category_id": category_id,
                                    }
                                ).execute()
                        st.success(
                            f"Exercise '{new_exercise_name_input}' added to library with tags: {', '.join(selected_categories) if selected_categories else 'None'}"
                        )
                        _get_exercise_library_data.clear() # Clear cache when new exercise is added
                        st.rerun()
                    else:
                        st.error(
                            f"Could not add '{new_exercise_name_input}'. It might already exist in the library or there was a database error."
                        )

                except Exception as e:
                    logger.error(
                        f"Error adding exercise '{new_exercise_name_input}' to library:"
                        f" {e}",
                        exc_info=True,
                    )
                    st.error(f"Failed to add exercise: {e}")
            else:
                st.warning("Please enter an exercise name.")

    if st.button("Cancel", key=f"cancel_add_exercise_form_{parent_key}"):
        st.rerun()  # Rerun to close the popover and clear the form


def render_edit_plan_page(logger):
    st.title("Macrocycle Planner")

    if st.button("⬅️ Back to Home"):
        st.session_state.page = "home"
        st.rerun()

    # --- 1. LIBRARY DATA ---
    exercise_library_data = _get_exercise_library_data()
    
    exercise_options = [f"{r[1]} [{r[2]}]" if r[2] else r[1] for r in exercise_library_data]
    name_lookup = {
        f"{r[1]} [{r[2]}]" if r[2] else r[1]: (r[1], r[0])
        for r in exercise_library_data
    }

    macro_name = st.text_input("Macro Name", value="", placeholder="New Plan (eg. Winter Bulk 26)")
    num_weeks = st.number_input("Weeks", 1, 52, 4)

    # --- 3. BUILDER ---
    if "workout_templates" not in st.session_state:
        st.session_state.workout_templates = []

    st.subheader("Workout Day Templates")

    add_day_col, _ = st.columns([0.2, 0.8])
    if add_day_col.button("➕ Add Day"):
        st.session_state.workout_templates.append(
            WorkoutTemplate(name=f"Day {len(st.session_state.workout_templates)+1}")
        )
        st.rerun()

    for workout_template_index, workout_template in enumerate(
        st.session_state.workout_templates
    ):
        with st.expander(
            f"Workout Template {workout_template_index+1}: {workout_template.name}",
            expanded=True,
        ):
            day_name_col, remove_day_col = st.columns([0.8, 0.2])
            workout_template.name = day_name_col.text_input(
                "Workout Name", value=workout_template.name, key=f"wname_{workout_template_index}"
            )
            if remove_day_col.button(
                "🗑️ Remove Day", key=f"remove_day_{workout_template_index}"
            ):
                st.session_state.workout_templates.pop(workout_template_index)
                st.rerun()

            exercises_to_render = list(workout_template.exercises)

            for exercise_index, exercise_template in enumerate(exercises_to_render):
                with st.container(border=True):
                    h_cols = st.columns([2, 0.5, 0.5])

                    current_exercise_name = exercise_template.name
                    default_index = 0
                    if current_exercise_name:
                        for i, option in enumerate(exercise_options):
                            if "[" in option:
                                option_name = option.split(" [")[0]
                            else:
                                option_name = option

                            if option_name == current_exercise_name:
                                default_index = i + 1
                                break

                    h_cols[0].selectbox(
                        "Lift Name",
                        ["(Select Exercise)"] + exercise_options,
                        key=f"lib_ex_{workout_template_index}_{exercise_index}",
                        on_change=_apply_exercise_choice,
                        args=(workout_template_index, exercise_index, name_lookup),
                        index=default_index,
                    )

                    with h_cols[1].popover("➕ Add New Exercise", use_container_width=True):
                        render_add_exercise_form(
                            logger,
                            parent_key=f"add_new_ex_{workout_template_index}_{exercise_index}",
                        )

                    if h_cols[2].button(
                        "🗑️ Remove Lift", key=f"del_{workout_template_index}_{exercise_index}"
                    ):
                        workout_template.exercises.pop(exercise_index)
                        st.rerun()

                    st.write("Sets:")
                    sets_cols = st.columns([0.5, 0.25, 0.25])
                    current_sets = exercise_template.sets

                    sets_cols[0].write(f"**{current_sets}**")

                    if sets_cols[1].button(
                        "➖", key=f"minus_set_{workout_template_index}_{exercise_index}"
                    ):
                        if exercise_template.sets > 1:
                            exercise_template.sets -= 1
                            exercise_template.rirs = exercise_template.rirs[: exercise_template.sets]
                            st.rerun()

                    if sets_cols[2].button(
                        "➕", key=f"add_set_{workout_template_index}_{exercise_index}"
                    ):
                        if exercise_template.sets < 20:
                            exercise_template.sets += 1
                            exercise_template.rirs.append(2)
                            st.rerun()

                    st.write("Set Plan:")
                    cols = st.columns(exercise_template.sets)
                    for set_index in range(exercise_template.sets):
                        rir_key = (
                            f"rir_{workout_template_index}_{exercise_index}_{set_index}"
                        )

                        while len(exercise_template.rirs) <= set_index:
                            exercise_template.rirs.append(2)

                        set_col = cols[set_index]
                        rir_input_col, rir_text_col = set_col.columns([0.7, 0.3])

                        current_rir_value = exercise_template.rirs[set_index]

                        exercise_template.rirs[set_index] = rir_input_col.number_input(
                            f"Set {set_index+1}",
                            min_value=0,
                            max_value=5,
                            value=current_rir_value,
                            key=rir_key,
                            label_visibility="collapsed",
                        )
                        rir_text_col.markdown("RIR")

                    exercise_template.notes = st.text_area(
                        "Notes", value=exercise_template.notes, key=f"note_{workout_template_index}_{exercise_index}"
                    )

            if st.button(
                f"➕ Add Exercise to {workout_template.name}", key=f"add_{workout_template_index}"
            ):
                workout_template.exercises.append(ExerciseTemplate())
                st.rerun()

    # --- 4. GENERATE ---
    st.divider()
    if st.button("Generate Plan for Macrocycle", type="primary", use_container_width=True):
        try:
            if not macro_name:
                st.error("Please enter a macro name.")
                return

            missing_exercises = []
            for workout_template in st.session_state.workout_templates:
                for exercise_template in workout_template.exercises:
                    if exercise_template.name:
                        found = False
                        for display_name, (ex_name, ex_id) in name_lookup.items():
                            if ex_name == exercise_template.name:
                                exercise_template.library_id = ex_id
                                found = True
                                break
                        if not found:
                            missing_exercises.append(exercise_template.name)

            if missing_exercises:
                st.error(
                    f"Cannot save plan: The following exercises are not in the library or have empty names: {', '.join(set(missing_exercises))}. Please add them via an admin interface or select from the library."
                )
                return

            # Insert MacroCycle
            macro_response = (
                _get_supabase_client_resource().table("macrocycles")
                .insert({"name": macro_name})
                .execute()
            )
            if not macro_response.data:
                raise Exception("Failed to insert MacroCycle")
            macro_cycle_id = macro_response.data[0]["id"]

            for week_num in range(1, int(num_weeks) + 1):
                mini_response = (
                    _get_supabase_client_resource().table("minicycles")
                    .insert(
                        {"macro_id": macro_cycle_id, "name": f"Week {week_num}"}
                    )
                    .execute()
                )
                if not mini_response.data:
                    raise Exception(f"Failed to insert MiniCycle for week {week_num}")
                mini_cycle_id = mini_response.data[0]["id"]

                for workout_template_index, workout_template in enumerate(
                    st.session_state.workout_templates
                ):
                    workout_response = (
                        _get_supabase_client_resource().table("workouts")
                        .insert(
                            {"mini_id": mini_cycle_id, "name": workout_template.name}
                        )
                        .execute()
                    )
                    if not workout_response.data:
                        raise Exception(f"Failed to insert Workout {workout_template.name}")
                    workout_id = workout_response.data[0]["id"]

                    for exercise_template in workout_template.exercises:
                        if not hasattr(exercise_template, "library_id"):
                            lib_lookup_response = (
                                _get_supabase_client_resource().table("exerciselibrary")
                                .select("id")
                                .eq("name", exercise_template.name)
                                .execute()
                            )
                            if lib_lookup_response.data:
                                exercise_template.library_id = lib_lookup_response.data[0]["id"]
                            else:
                                raise ValueError(
                                    f"Exercise '{exercise_template.name}' not found in library during final save."
                                )

                        _get_supabase_client_resource().table("plannedexercises").insert(
                            {
                                "workout_id": workout_id,
                                "exercise_library_id": exercise_template.library_id,
                                "sets": exercise_template.sets,
                                "target_rir_json": exercise_template.rirs,
                                "notes": exercise_template.notes,
                            }
                        ).execute()
            st.success("Plan Saved!")

            # Clear relevant caches from view_plan_page
            _fetch_macro_cycles.clear()
            _fetch_full_macro_cycle_details.clear()
            render_sidebar_stats.clear()

            for key in list(st.session_state.keys()):
                if (
                    key.startswith("wname_")
                    or key.startswith("lib_ex_")
                    or key.startswith("ex_name_input_")
                    or key.startswith("set_count_")
                    or key.startswith("rir_")
                    or key.startswith("note_")
                ):
                    del st.session_state[key]
            st.session_state.workout_templates = []
            st.rerun()

        except Exception as e:
            st.error(f"Failed to save plan: {e}")
            logger.error(f"Plan generation failed: {e}", exc_info=True)
