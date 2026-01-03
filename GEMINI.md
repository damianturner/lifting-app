# Gemini Project Context: Lifting App

This document provides context for the Lifting App project for the Gemini AI assistant.

## Project Overview

This project is a Streamlit web application created for tracking lifting programs and progress. It uses a SQLite database to store workout data.

## Tech Stack

-   **Language:** Python
-   **Framework:** Streamlit
-   **Libraries:** pandas
-   **Database:** SQLite

## How to Run

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run the application:**
    ```bash
    streamlit run app.py
    ```

The application will be available at `http://localhost:8501`.

## Database Schema

The database schema is defined in `schema.sql`.

## Project Structure

-   `app.py`: The main entry point of the Streamlit application. It handles routing and page rendering.
-   `requirements.txt`: The list of Python dependencies.
-   `schema.sql`: The SQL schema for the database.
-   `init.py`: Contains initialization code for logging and the database.
-   `pages/`: Contains the different pages of the Streamlit application.
    -   `view_plan_page.py`: Renders the page for viewing workout plans.
    -   `edit_plan_page.py`: Renders the page for creating or editing workout plans.
-   `.data/fitness.db`: The SQLite database file.
-   `.streamlit/config.toml`: Configuration for Streamlit.
-   `test/`: Contains tests.
-   `TODO.md`: A list of tasks to be done.
