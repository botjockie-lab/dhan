"""
Helper script to sync code to a remote VPS and manage the systemd service.
Useful for local development while executing in a remote environment.

Before using, update the CONFIGURATION section below with your VPS details:
- REMOTE_HOST: IP address or hostname of your VPS
- REMOTE_USER: SSH username on the VPS
- SSH_KEY: Path to your SSH private key (or None to use default/agent)

Usage:
    python remote_runner.py           # Sync code and restart service (Dev mode)
    python remote_runner.py start     # Start remote systemd service
    python remote_runner.py stop      # Stop remote systemd service
    python remote_runner.py restart   # Restart remote systemd service
    python remote_runner.py status    # Check service status
    python remote_runner.py log       # Tail service logs
"""
import os
import subprocess
import sys
import argparse

# ==============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ==============================================================================
REMOTE_HOST = "<VPS_IP_ADDRESS>"       # IP address of your VPS (e.g., "192.168.1.100" or cloud VM IP)
REMOTE_USER = "<VPS_USERNAME>"        # SSH username (e.g., "ubuntu", "ec2-user")
REMOTE_DIR = "~/dhan"     # Directory on the VPS to deploy to
SSH_KEY = None  # Path to SSH private key, or None to use default ~/.ssh/id_rsa or SSH agent
                # Example: r"C:\Users\YourUsername\.ssh\id_ed25519" on Windows
                #          "~/.ssh/id_ed25519" on Linux/Mac
SERVICE_NAME = "dhan.service"         # Name of the systemd service

# Files to sync (whitelist approach)
INCLUDE_EXTENSIONS = ('.py', '.env', '.txt', '.json', '.service', '.example')
EXCLUDE_FILES = ('remote_runner.py', 'dryrun.log')

# Remote command to execute (Dev mode)
REMOTE_PYTHON = "python3"
MAIN_SCRIPT = "dhan_risk_manager.py"
# ==============================================================================

def get_ssh_base():
    cmd = ["ssh"]
    if SSH_KEY:
        cmd.extend(["-i", SSH_KEY])
    return cmd

def run_ssh_command(command, interactive=False):
    """Runs a command on the remote host via SSH."""
    ssh_cmd = get_ssh_base()
    
    if interactive:
        ssh_cmd.append("-t") # Allocate pseudo-terminal
        
    ssh_cmd.extend([f"{REMOTE_USER}@{REMOTE_HOST}", command])
    
    try:
        return subprocess.call(ssh_cmd)
    except KeyboardInterrupt:
        print("\n[Local] Interrupted.")
        return 1

def sync_files():
    """Syncs local files to the remote directory."""
    # 1. Identify files
    local_files = [
        f for f in os.listdir('.') 
        if os.path.isfile(f) 
        and f.lower().endswith(INCLUDE_EXTENSIONS) 
        and f not in EXCLUDE_FILES
    ]
    
    if not local_files:
        print("No files found to sync.")
        return False

    print(f"Found {len(local_files)} files to sync: {', '.join(local_files)}")

    # 2. Ensure remote directory exists
    print(f"\n[Sync] Ensuring remote directory exists: {REMOTE_DIR}")
    if run_ssh_command(f"mkdir -p {REMOTE_DIR}") != 0:
        print("Error creating remote directory.")
        return False

    # 3. Sync files via SCP
    print(f"\n[Sync] Copying files to {REMOTE_HOST}...")
    scp_cmd = ["scp"]
    if SSH_KEY:
        scp_cmd.extend(["-i", SSH_KEY])
    
    scp_cmd.extend(local_files)
    scp_cmd.append(f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_DIR}")
    
    if subprocess.call(scp_cmd) != 0:
        print("SCP failed.")
        return False
        
    return True

def handle_service(action):
    """Controls the remote systemd service."""
    cmds = {
        "start": f"sudo systemctl start {SERVICE_NAME}",
        "stop": f"sudo systemctl stop {SERVICE_NAME}",
        "restart": f"sudo systemctl restart {SERVICE_NAME}",
        "status": f"sudo systemctl status {SERVICE_NAME}",
        "log": f"journalctl -u {SERVICE_NAME} -f"
    }
    
    if action not in cmds:
        print(f"Unknown action: {action}")
        return

    print(f"\n[Service] Executing: {action.upper()} {SERVICE_NAME}...")
    run_ssh_command(cmds[action], interactive=(action == "log"))

def main():
    parser = argparse.ArgumentParser(description="Remote Runner & Service Manager")
    parser.add_argument("command", nargs="?", default="dev", 
                        choices=["dev", "start", "stop", "restart", "status", "log"],
                        help="Action to perform. 'dev' (default) syncs and runs the script interactively.")
    
    args = parser.parse_args()

    if args.command == "dev":
        if sync_files():
            print(f"\n[Dev] Running {MAIN_SCRIPT} on remote...")
            print("="*60)
            # run_ssh_command(f"cd {REMOTE_DIR} &&  {REMOTE_PYTHON} {MAIN_SCRIPT}", interactive=True)
            handle_service("restart")
    else:
        # For service commands, we usually don't sync files implicitly, 
        # but you might want to sync on restart. 
        # For now, let's keep them separate or maybe sync on restart?
        # User asked for start/stop. Let's keep it simple: specific command does specific thing.
        # If they want to deploy code and restart, they might need a deploy command.
        # For this request, strictly mapped service commands.
        handle_service(args.command)

if __name__ == "__main__":
    main()