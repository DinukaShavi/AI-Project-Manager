import os
import sys
from alembic.config import Config
from alembic import command

def run_test():
    print("Initializing migration validation test...")
    # Navigate to the backend directory where alembic.ini resides
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = os.path.join(project_root, "backend")
    os.chdir(backend_dir)
    
    # Configure Alembic
    alembic_cfg = Config("alembic.ini")
    
    try:
        # Step 1: Rollback to base first
        print("\nStep 1: Testing Downgrade to base...")
        command.downgrade(alembic_cfg, "base")
        print("SUCCESS: Downgrade completed.")
        
        # Step 2: Upgrade to head
        print("\nStep 2: Testing Upgrade to head...")
        command.upgrade(alembic_cfg, "head")
        print("SUCCESS: Upgrade completed.")
        
        print("\nMigration test completed successfully! Database schema rollback and upgrade are fully compliant.")
    except Exception as e:
        print(f"\nERROR: Migration test failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_test()
