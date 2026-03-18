import PyInstaller.__main__
import shutil
import os

# Clean previous builds
if os.path.exists("dist"):
    shutil.rmtree("dist")
if os.path.exists("build"):
    shutil.rmtree("build")

print("Building Menu Zen Backend Launcher...")

# Define hidden imports needed for FastAPI/SQLAlchemy/Uvicorn
hidden_imports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "sqlalchemy.sql.default_comparator",
    "sqlalchemy.ext.asyncio",
    "engineio.async_drivers.asgi",  # If using socketio
    # Add other hidden imports as needed
]

args = [
    "launcher.py",  # Your main script
    "--name=MenuZenServer",
    "--console",   # Open terminal window (was --windowed)
    "--onedir",    # Create a directory (easier for debugging assets than --onefile)
    "--clean",
    # Include the app package
    "--add-data=app:app",
    # Include alembic if needed
    "--add-data=alembic:alembic",
    "--add-data=alembic.ini:.",
    # Include uploads or static files
    # "--add-data=uploads:uploads", 
]

for imp in hidden_imports:
    args.append(f"--hidden-import={imp}")

PyInstaller.__main__.run(args)

print("Build complete. check dist/MenuZenServer")
