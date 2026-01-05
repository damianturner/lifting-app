import streamlit as st
import logging
import json
from supabase import Client

logger = logging.getLogger(__name__)

def _fetch_macro_cycles(supabase_client: Client, logger):
    """Fetches all macro cycles for the current user from the database."""
    try:
        response = supabase_client.table("MacroCycles").select("id, name").execute()
        if response.data:
            return response.data
        else:
            return []
    except Exception as e:
        logger.error(f"Error fetching macro cycles: {e}", exc_info=True)
        st.error(f"Error fetching macro cycles: {e}")
        return []

def _select_macro_plan(macro_cycles):
    """Handles Streamlit selectbox for macro plans and returns selected macro details."""
    
    name_counts = {}
    for mc in macro_cycles:
        name_counts[mc["name"]] = name_counts.get(mc["name"], 0) + 1

    macro_display_options = []
    macro_display_to_id = {}

    for macro_cycle in macro_cycles:
        name = macro_cycle["name"]
        macro_id = macro_cycle["id"]
        
        display_name = name
        if name_counts[name] > 1:
            display_name = f"{name} (ID: {macro_id})"
        
        macro_display_options.append(display_name)
        macro_display_to_id[display_name] = macro_id

    if macro_display_options:
        selected_display_name = st.selectbox("Select a Plan", options=macro_display_options)
        macro_id = macro_display_to_id[selected_display_name]
        
        original_selected_macro_name = next((mc['name'] for mc in macro_cycles if mc['id'] == macro_id), selected_display_name)
    else:
        selected_display_name = None
        macro_id = None
        original_selected_macro_name = None

    return original_selected_macro_name, macro_id

def _fetch_mini_cycles_for_macro(supabase_client: Client, macro_id, logger):
    """Fetches mini cycles for a given macro ID."""
    try:
        response = supabase_client.table("MiniCycles").select("id, name").eq("macro_id", macro_id).execute()
        if response.data:
            return response.data
        else:
            return []
    except Exception as e:
        logger.error(f"Error fetching mini cycles for macro {macro_id}: {e}", exc_info=True)
        st.error(f"Error fetching mini cycles for macro {macro_id}: {e}")
        return []

def _fetch_workouts_for_mini(supabase_client: Client, mini_id, logger):
    """Fetches workouts for a given mini ID."""
    try:
        response = supabase_client.table("Workouts").select("id, name").eq("mini_id", mini_id).execute()
        if response.data:
            return response.data
        else:
            return []
    except Exception as e:
        logger.error(f"Error fetching workouts for mini {mini_id}: {e}", exc_info=True)
        st.error(f"Error fetching workouts for mini {mini_id}: {e}")
        return []

def _fetch_planned_exercises_for_workout(supabase_client: Client, workout_id, logger):
    """Fetches planned exercises for a given workout ID."""
    try:
        # Supabase client is a bit different for complex joins and aggregations.
        # We might need to fetch data and then process it, or use a view/function on Supabase.
        # For now, let's try to fetch related data.
        # This will fetch PlannedExercises with related ExerciseLibrary and Categories.
        response = supabase_client.table("PlannedExercises").select(
            "id, sets, target_rir_json, notes, exercise_library:ExerciseLibrary(name), "
            "exercise_categories:ExerciseCategories(category:Categories(name))"
        ).eq("workout_id", workout_id).execute()

        planned_exercises_data = []
        if response.data:
            for pe in response.data:
                exercise_name = pe['exercise_library']['name'] if pe['exercise_library'] else "Unknown Exercise"
                
                # Aggregate category names
                body_parts_list = []
                if pe['exercise_categories']:
                    for ec in pe['exercise_categories']:
                        if ec['category']:
                            body_parts_list.append(ec['category']['name'])
                body_parts = ", ".join(body_parts_list) if body_parts_list else None
                
                planned_exercises_data.append({
                    "exercise_name": exercise_name,
                    "sets": pe["sets"],
                    "target_rir_json": pe["target_rir_json"],
                    "notes": pe["notes"],
                    "body_parts": body_parts
                })
        return planned_exercises_data
    except Exception as e:
        logger.error(f"Error fetching planned exercises for workout {workout_id}: {e}", exc_info=True)
        st.error(f"Error fetching planned exercises for workout {workout_id}: {e}")
        return []

def _render_exercises_table(planned_exercises):
    """Renders a markdown table for the given planned exercises."""
    if planned_exercises:
        md_table = "| Exercise | Body Part | Sets | Target RIR (per set) | Notes |\n"
        md_table += "| :--- | :--- | :--- | :--- | :--- |\n"
        
        for planned_exercise in planned_exercises:
            try:
                rir_list = planned_exercise["target_rir_json"] if isinstance(planned_exercise["target_rir_json"], list) \
                             else (json.loads(planned_exercise["target_rir_json"]) if planned_exercise["target_rir_json"] else [])
                rir_display = " / ".join(map(str, rir_list))
                rir_display = rir_display.replace("|", "&#124;") if rir_display else "—"
                
                safe_notes = str(planned_exercise["notes"]).replace("\n", " ") if planned_exercise["notes"] else ""
                safe_notes = safe_notes.replace("|", "&#124;")
                safe_parts = f"`{planned_exercise['body_parts']}`" if planned_exercise["body_parts"] else "—"
                
                exercise_name_sanitized = planned_exercise['exercise_name'].replace("|", "&#124;")
                
                md_table += f"| **{exercise_name_sanitized}** | {safe_parts} | {planned_exercise['sets']} | {rir_display} | {safe_notes} |\n"
            except json.JSONDecodeError:
                exercise_name_sanitized = planned_exercise['exercise_name'].replace("|", "&#124;")
                md_table += f"| **{exercise_name_sanitized}** | Error | Data Corruption | Check DB | |\n"
        
        st.markdown(md_table)
    else:
        st.info("No exercises added to this workout blueprint.")

def _render_danger_zone(supabase_client: Client, selected_macro_name, macro_id, logger):
    """Renders the danger zone section for plan deletion."""
    st.divider()
    with st.expander("⚠️ Danger Zone"):
        st.write(f"Permanently delete the plan: **{selected_macro_name}**")
        if st.button(f"Confirm Delete {selected_macro_name}", type="primary"):
            try:
                # Deleting MacroCycles should cascade to MiniCycles, Workouts, PlannedExercises, etc.
                response = supabase_client.table("MacroCycles").delete().eq("id", macro_id).execute()
                if response.data:
                    st.success("Plan deleted successfully!")
                    st.rerun()
                else:
                    logger.error(f"No data returned on delete for macro_id {macro_id}. Response: {response}")
                    st.error("Could not delete plan.")
            except Exception as e:
                logger.error(f"Delete failed: {e}", exc_info=True)
                st.error("Could not delete plan.")

def render_view_plan_page(supabase_client: Client, logger):
    st.title("Planned Macrocycles")
    
    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()

    macro_cycles = _fetch_macro_cycles(supabase_client, logger)
    
    if not macro_cycles:
        st.warning("No plans found in the database for your user.")
        return

    selected_macro_name, macro_id = _select_macro_plan(macro_cycles)

    mini_cycles = _fetch_mini_cycles_for_macro(supabase_client, macro_id, logger)

    if mini_cycles:
        tabs = st.tabs([mini_cycle["name"] for mini_cycle in mini_cycles])
        
        for tab, mini_cycle in zip(tabs, mini_cycles):
            with tab:
                workouts = _fetch_workouts_for_mini(supabase_client, mini_cycle["id"], logger)
                
                if not workouts:
                    st.write("No workouts scheduled for this week.")

                for workout in workouts:
                    workout_id = workout["id"]
                    workout_name = workout["name"]
                    with st.expander(f"🏋️ {workout_name}", expanded=True):
                        planned_exercises = _fetch_planned_exercises_for_workout(supabase_client, workout_id, logger)
                        _render_exercises_table(planned_exercises)
    
    _render_danger_zone(supabase_client, selected_macro_name, macro_id, logger)


def render_sidebar_stats(supabase_client: Client, logger):
    with st.sidebar:
        st.subheader("Database Stats")
        try:
            response = supabase_client.table("MacroCycles").select("count").execute()
            if response.data and isinstance(response.data, list) and len(response.data) > 0:
                # Supabase count returns a list with a single dict, e.g., [{'count': 5}]
                count = response.count # Access count directly from the response object
                st.metric("Total Plans Saved", count)
            else:
                st.metric("Total Plans Saved", 0)
        except Exception as e:
            logger.error(f"Error fetching sidebar stats: {e}", exc_info=True)
            st.sidebar.error("Stats unavailable")
