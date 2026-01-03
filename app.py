import streamlit as st
import os
from init import setup_logging, init_db
from view_plan_page import render_view_plan_page, render_sidebar_stats
from edit_plan_page import render_edit_plan_page

# 1. SETUP & CONFIG
DB_PATH = os.path.join(".data", "fitness.db")

# Initialize Logger and Database
logger = setup_logging()
init_db(DB_PATH, logger)

# 2. SIDEBAR TOOLS (Logs & Stats)
def render_sidebar_tools():
    render_sidebar_stats(DB_PATH)
    with st.sidebar:
        st.divider()
        st.subheader("🛠️ Internal Logs")
        log_text = st.session_state.log_buffer.getvalue()
        st.text_area("Debug Console", value=log_text, height=200, disabled=True)
        if st.button("Clear Logs"):
            st.session_state.log_buffer.truncate(0)
            st.session_state.log_buffer.seek(0)
            st.rerun()

render_sidebar_tools()

# 3. ROUTING LOGIC
if 'page' not in st.session_state:
    st.session_state.page = 'home'

if st.session_state.page == 'home':
    st.title("🏋️ Workout Architect")
    col1, col2 = st.columns(2)
    if col1.button("📂 View Plans", use_container_width=True):
        st.session_state.page = 'view_plan'
        st.rerun()
    if col2.button("🏗️ Create New Plan", use_container_width=True):
        st.session_state.page = 'edit_plan'
        st.rerun()

elif st.session_state.page == 'view_plan':
    render_view_plan_page(DB_PATH)

elif st.session_state.page == 'edit_plan':
    render_edit_plan_page(DB_PATH)