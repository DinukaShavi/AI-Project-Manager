import os

backend_dirs = [
    "backend/app/api",
    "backend/app/core",
    "backend/app/models",
    "backend/app/schemas",
    "backend/app/services",
    "backend/app/repositories",
    "backend/app/crud",
    "backend/app/agents",
    "backend/app/tools",
    "backend/app/workflows",
    "backend/app/integrations",
    "backend/app/events",
    "backend/app/memory",
    "backend/app/analytics",
    "backend/app/workers",
]

frontend_dirs = [
    "frontend/app",
    "frontend/components",
    "frontend/hooks",
    "frontend/lib",
    "frontend/stores",
    "frontend/types",
    "frontend/services",
]

other_dirs = [
    "infrastructure",
    "docs",
    "scripts",
]

# Create directories and add __init__.py files where appropriate
for directory in backend_dirs:
    os.makedirs(directory, exist_ok=True)
    init_file = os.path.join(directory, "__init__.py")
    with open(init_file, "w") as f:
        pass
    print(f"Created backend package directory: {directory}")

# Initialize app level __init__.py
app_init = "backend/app/__init__.py"
with open(app_init, "w") as f:
    pass

for directory in frontend_dirs:
    os.makedirs(directory, exist_ok=True)
    print(f"Created frontend directory: {directory}")

for directory in other_dirs:
    os.makedirs(directory, exist_ok=True)
    print(f"Created other directory: {directory}")

print("Folder setup complete.")
