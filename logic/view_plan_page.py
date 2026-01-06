import streamlit as st
import logging
import json
from init import _get_supabase_client_resource # Import the cached resource client

logger = logging.getLogger(__name__)

@st.cache_data(ttl=3600) # Cache for 1 hour
def _fetch_macro_cycles():
    """Fetches all macro cycles for the current user from the database."""
    supabase_client = _get_supabase_client_resource()
    logger = logging.getLogger(__name__)
    try:
        response = supabase_client.table("macrocycles").select("id, name").execute()
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

@st.cache_data(ttl=3600) # Cache for 1 hour
def _fetch_full_macro_cycle_details(macro_id):
    """Fetches a single macro cycle and all its nested children in one query."""
    supabase_client = _get_supabase_client_resource()
    logger = logging.getLogger(__name__)
    try:
        query = """
            id, name,
            minicycles (
                id, name,
                workouts (
                    id, name,
                    plannedexercises (
                        id, sets, target_rir_json, notes,
                        exercise_library:exerciselibrary ( 
                            name,
                            exercise_categories:exercisecategories ( 
                                category:categories ( name ) 
                            )
                        )
                    )
                )
            )
        """
        response = supabase_client.table("macrocycles").select(query).eq("id", macro_id).single().execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching full macro cycle details for macro_id {macro_id}: {e}", exc_info=True)
        st.error(f"An error occurred while loading the plan details: {e}")
        return None

def _render_exercises_table(planned_exercises):
    """Renders a markdown table for the given planned exercises."""
    if planned_exercises:
        md_table = "| Exercise | Body Part | Sets | Target RIR (per set) | Notes |\n"
        md_table += "| :--- | :--- | :--- | :--- | :--- |\n"
        
        for planned_exercise in planned_exercises:
            try:
                # Safely access nested data
                exercise_name = planned_exercise.get('exercise_library', {}).get('name') or "Unknown Exercise"
                
                # Aggregate category names
                body_parts_list = []
                if planned_exercise.get('exercise_library', {}).get('exercise_categories'):
                    for ec in planned_exercise['exercise_library']['exercise_categories']:
                        if ec.get('category'):
                            body_parts_list.append(ec['category']['name'])
                body_parts = ", ".join(body_parts_list) if body_parts_list else None

                rir_list = planned_exercise["target_rir_json"] if isinstance(planned_exercise["target_rir_json"], list) \
                             else (json.loads(planned_exercise["target_rir_json"]) if planned_exercise["target_rir_json"] else [])
                rir_display = " / ".join(map(str, rir_list))
                rir_display = rir_display.replace("|", "&#124;") if rir_display else "—"
                
                safe_notes = str(planned_exercise["notes"]).replace("\n", " ") if planned_exercise["notes"] else ""
                safe_notes = safe_notes.replace("|", "&#124;")
                safe_parts = f"`{body_parts}`" if body_parts else "—"
                
                exercise_name_sanitized = exercise_name.replace("|", "&#124;")
                
                md_table += f"| **{exercise_name_sanitized}** | {safe_parts} | {planned_exercise['sets']} | {rir_display} | {safe_notes} |\n"
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error processing planned exercise: {e}. Data: {planned_exercise}")
                exercise_name_sanitized = str(planned_exercise.get('exercise_library', 'Error')).replace("|", "&#124;")
                md_table += f"| **{exercise_name_sanitized}** | Error | Data Corruption | Check DB | |\n"
        
        st.markdown(md_table)
    else:
        st.info("No exercises added to this workout blueprint.")

def _render_danger_zone(selected_macro_name, macro_id, logger):
    """Renders the danger zone section for plan deletion."""
    st.divider()
    with st.expander("⚠️ Danger Zone"):
        st.write(f"Permanently delete the plan: **{selected_macro_name}**")
        if st.button(f"Confirm Delete {selected_macro_name}", type="primary"):
            try:
                # Deleting MacroCycles should cascade to MiniCycles, Workouts, PlannedExercises, etc.
                response = _get_supabase_client_resource().table("macrocycles").delete().eq("id", macro_id).execute()
                if response.data:
                    st.success("Plan deleted successfully!")
                    # Clear caches after successful deletion
                    _fetch_macro_cycles.clear()
                    _fetch_full_macro_cycle_details.clear()
                    render_sidebar_stats.clear() # Clear stats cache as count changes
                    st.rerun()
                else:
                    logger.error(f"No data returned on delete for macro_id {macro_id}. Response: {response}")
                    st.error("Could not delete plan.")
            except Exception as e:
                logger.error(f"Delete failed: {e}", exc_info=True)
                st.error("Could not delete plan.")

def render_view_plan_page(logger):
    st.title("Planned Macrocycles")
    
    if st.button("⬅️ Back to Home"):
        st.session_state.page = 'home'
        st.rerun()

    macro_cycles = _fetch_macro_cycles()
    
    if not macro_cycles:
        st.warning("No plans found in the database for your user.")
        return

    selected_macro_name, macro_id = _select_macro_plan(macro_cycles)

    # If a macro_id is selected, fetch all its details in one go.
    if macro_id:
        full_macro_details = _fetch_full_macro_cycle_details(macro_id)

        if full_macro_details and full_macro_details.get('minicycles'):
            mini_cycles = full_macro_details['minicycles']
            
            # Sort minicycles by name to ensure consistent order
            mini_cycles.sort(key=lambda x: x.get('name', ''))

            tabs = st.tabs([mini_cycle.get("name", "Unnamed Week") for mini_cycle in mini_cycles])
            
            for tab, mini_cycle in zip(tabs, mini_cycles):
                with tab:
                    workouts = mini_cycle.get('workouts', [])
                    if not workouts:
                        st.write("No workouts scheduled for this week.")
                        continue
                    
                    # Sort workouts by name
                    workouts.sort(key=lambda x: x.get('name', ''))

                    for workout in workouts:
                        workout_name = workout.get("name", "Unnamed Workout")
                        with st.expander(f"🏋️ {workout_name}", expanded=True):
                            planned_exercises = workout.get('plannedexercises', [])
                            # Sort exercises by ID (creation order)
                            planned_exercises.sort(key=lambda x: x.get('id', 0))
                            _render_exercises_table(planned_exercises)
        else:
            st.info("This plan has no scheduled weeks (mini-cycles).")
    
    if selected_macro_name and macro_id:
        _render_danger_zone(selected_macro_name, macro_id, logger)


def render_sidebar_stats():
    supabase_client = _get_supabase_client_resource()
    logger = logging.getLogger(__name__)
    with st.sidebar:
        st.subheader("Database Stats")
        try:
            # Using PostgREST's exact count method
            response = supabase_client.table("macrocycles").select("id", count='exact').execute()
            count = response.count if hasattr(response, 'count') else 0
            st.metric("Total Plans Saved", count)
        except Exception as e:
            logger.error(f"Error fetching sidebar stats: {e}", exc_info=True)
            st.sidebar.error("Stats unavailable")
