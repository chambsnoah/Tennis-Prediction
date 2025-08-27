#!/usr/bin/env python3
"""
Dependency management script for tennis_api package.

Usage:
    python deps.py compile    # Generate requirements.txt from requirements.in
    python deps.py sync       # Install exact versions from requirements.txt
    python deps.py upgrade    # Upgrade all dependencies and recompile
    python deps.py check      # Check current dependency versions
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, cwd=None, timeout=30):
    """Run a command and handle errors with timeout."""
    try:
        result = subprocess.run(cmd, shell=True, check=True, cwd=cwd, 
                              capture_output=True, text=True, timeout=timeout)
        print(result.stdout)
        return True
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds: {cmd}")
        print("Try running the command manually or check network connectivity.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Return code: {e.returncode}")
        print(f"Error output: {e.stderr}")
        return False

def ensure_pip_tools():
    """Ensure pip-tools is installed."""
    try:
        result = subprocess.run(["pip", "show", "pip-tools"], 
                               capture_output=True, text=True)
        if result.returncode == 0:
            return True
    except Exception:
        pass
    
    print("Installing pip-tools...")
    return run_command("pip install pip-tools")

def compile_requirements():
    """Compile requirements.in to requirements.txt with hashes."""
    if not ensure_pip_tools():
        return False
    
    print("Compiling requirements.in to requirements.txt...")
    script_dir = Path(__file__).parent
    
    # Try with timeout first
    if run_command("pip-compile --generate-hashes requirements.in", cwd=script_dir, timeout=60):
        return True
    
    print("\nFailed to generate with hashes. Trying without hashes...")
    if run_command("pip-compile requirements.in", cwd=script_dir, timeout=60):
        return True
    
    print("\nFailed to use pip-compile. The current requirements.txt has upper bounds")
    print("which provides protection against breaking changes.")
    print("You can try running pip-compile manually when network conditions improve.")
    return False

def sync_requirements():
    """Install exact versions from requirements.txt."""
    if not ensure_pip_tools():
        print("pip-tools not available, using regular pip install...")
        script_dir = Path(__file__).parent
        return run_command("pip install -r requirements.txt", cwd=script_dir)
    
    print("Syncing dependencies from requirements.txt...")
    script_dir = Path(__file__).parent
    return run_command("pip-sync requirements.txt", cwd=script_dir)

def upgrade_requirements():
    """Upgrade all dependencies and recompile."""
    if not ensure_pip_tools():
        return False
    
    print("Upgrading all dependencies...")
    script_dir = Path(__file__).parent
    if run_command("pip-compile --upgrade requirements.in", cwd=script_dir, timeout=60):
        print("Dependencies upgraded successfully!")
        return True
    return False

def check_requirements():
    """Check current versions of core dependencies."""
    print("Checking current dependency versions...")
    dependencies = ["requests", "aiohttp", "python-dateutil"]
    
    for dep in dependencies:
        try:
            result = subprocess.run(["pip", "show", dep], 
                                   capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if line.startswith('Version:'):
                        version = line.split(':', 1)[1].strip()
                        print(f"{dep}: {version}")
                        break
            else:
                print(f"{dep}: Not installed")
        except Exception as e:
            print(f"{dep}: Error checking version - {e}")
    
    return True

def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "compile":
        success = compile_requirements()
    elif command == "sync":
        success = sync_requirements()
    elif command == "upgrade":
        success = upgrade_requirements()
    elif command == "check":
        success = check_requirements()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
    
    if not success:
        sys.exit(1)
    
    print(f"Command '{command}' completed successfully!")

if __name__ == "__main__":
    main()