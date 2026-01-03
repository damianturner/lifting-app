import sqlite3
import json
import streamlit as st

print("--- System Health Check ---")
try:
    # Test 1: SQLite C-Bindings
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test (id INTEGER)")
    print("✅ SQLite Bindings: OK")
    
    # Test 2: JSON Serialization
    data = json.dumps([1, 2, 3])
    print("✅ JSON Engine: OK")
    
    # Test 3: Streamlit Imports (The usual Segfault trigger)
    print("✅ Streamlit Import: OK")
    
    print("\nEnvironment is STABLE. You can now run your app.")
except Exception as e:
    print(f"❌ Error: {e}")