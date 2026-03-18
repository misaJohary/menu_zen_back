import sys
import os
import webbrowser
import uvicorn
import time
import threading

# Configuration
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
SERVER_URL = f"http://localhost:{SERVER_PORT}"

def start_server():
    print(f"Starting server at {SERVER_URL}...")
    print("Press Ctrl+C to stop the server.")
    
    # Open browser after a short delay
    def open_browser():
        time.sleep(2)
        print("Opening browser...")
        webbrowser.open(SERVER_URL)
    
    threading.Thread(target=open_browser, daemon=True).start()

    # Import app here to avoid issues if imports fail at top level
    try:
        from app.main import app as fastapi_app
        uvicorn.run(fastapi_app, host=SERVER_HOST, port=SERVER_PORT)
    except Exception as e:
        print(f"Error starting server: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    start_server()
