#!/usr/bin/env python3
import os
import sys
import time
import signal
import psutil
import argparse
import requests
import logging
import threading
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/var/log/ml-monitor.log',
    filemode='a'
)
logger = logging.getLogger('ml-monitor')

class MLMonitorDaemon:
    def __init__(self, ntfy_server, ntfy_topic="phone_only", check_interval=5):
        self.ntfy_server = ntfy_server
        self.ntfy_topic = ntfy_topic
        self.check_interval = check_interval
        self.tracked_processes = {}  # {pid: {'cmdline': cmd, 'start_time': time, 'username': user}}
        self.stop_event = threading.Event()
        
    def find_python_processes(self):
        """Find all running Python processes"""
        new_processes = {}
        
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cmdline', 'create_time']):
            try:
                # Check if this is a Python process
                if proc.info['name'] == 'python' or proc.info['name'] == 'python3':
                    pid = proc.info['pid']
                    
                    # Skip if we're already tracking this process
                    if pid in self.tracked_processes:
                        new_processes[pid] = self.tracked_processes[pid]
                        continue
                    
                    # Skip if this is our own process
                    if pid == os.getpid():
                        continue
                        
                    # Get command line as string
                    cmdline = " ".join(proc.info['cmdline']) if proc.info['cmdline'] else "Unknown"
                    
                    # Track only main processes (not child processes)
                    # A main process typically has a parent that is not a Python process
                    try:
                        parent = psutil.Process(proc.ppid())
                        parent_name = parent.name()
                        if parent_name in ['python', 'python3']:
                            # This is likely a child process, skip it
                            continue
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    
                    # Store process info for tracking
                    new_processes[pid] = {
                        'cmdline': cmdline,
                        'start_time': datetime.fromtimestamp(proc.info['create_time']),
                        'username': proc.info['username'],
                        'last_checked': datetime.now(),
                        'gpu_info': self.get_gpu_info_for_process(pid)
                    }
                    
                    logger.info(f"Started tracking Python process {pid}: {cmdline}")
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        return new_processes
    
    def get_gpu_info_for_process(self, pid):
        """Get GPU usage information for a process using nvidia-smi"""
        try:
            # This tries to use nvidia-smi to get GPU information
            import subprocess
            result = subprocess.run(
                ['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader'],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                return None
                
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 2 and parts[0].strip() == str(pid):
                    return {'used_memory': parts[1].strip()}
            
            return None
        except Exception as e:
            logger.debug(f"Failed to get GPU info: {e}")
            return None
    
    def check_process_status(self):
        """Check if any tracked processes have terminated"""
        current_pids = set(self.tracked_processes.keys())
        terminated_pids = []
        
        for pid in current_pids:
            try:
                proc = psutil.Process(pid)
                # Update last checked time
                self.tracked_processes[pid]['last_checked'] = datetime.now()
                # Update GPU info
                self.tracked_processes[pid]['gpu_info'] = self.get_gpu_info_for_process(pid)
            except psutil.NoSuchProcess:
                # Process has terminated
                process_info = self.tracked_processes[pid]
                end_time = datetime.now()
                duration = end_time - process_info['start_time']
                
                # Send notification
                title = f"ML Process Ended - {process_info['username']}"
                message = (
                    f"Command: {process_info['cmdline']}\n"
                    f"Duration: {duration}\n"
                    f"Start time: {process_info['start_time']}\n"
                    f"End time: {end_time}"
                )
                
                self.send_notification(title, message)
                logger.info(f"Process {pid} terminated after running for {duration}")
                
                # Mark for removal
                terminated_pids.append(pid)
        
        # Remove terminated processes
        for pid in terminated_pids:
            del self.tracked_processes[pid]
    
    def send_notification(self, title, message):
        """Send notification via ntfy"""
        url = f"https://{self.ntfy_server}/{self.ntfy_topic}"
        try:
            headers = {
                "Title": title,
                "Priority": "high",
                "Tags": "computer,white_check_mark"
            }
            response = requests.post(url, data=message.encode('utf-8'), headers=headers)
            if response.status_code == 200:
                logger.info(f"Notification sent: {title}")
            else:
                logger.error(f"Failed to send notification: {response.status_code}, {response.text}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False
    
    def save_state(self, state_file="/var/lib/ml-monitor/state.json"):
        """Save the current state to a file"""
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        
        # Convert datetime objects to strings
        serializable_state = {}
        for pid, info in self.tracked_processes.items():
            serializable_state[str(pid)] = {
                'cmdline': info['cmdline'],
                'start_time': info['start_time'].isoformat(),
                'username': info['username'],
                'last_checked': info['last_checked'].isoformat(),
                'gpu_info': info['gpu_info']
            }
        
        try:
            with open(state_file, 'w') as f:
                json.dump(serializable_state, f)
            logger.debug(f"State saved: {len(serializable_state)} processes")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def load_state(self, state_file="/var/lib/ml-monitor/state.json"):
        """Load state from a file"""
        if not os.path.exists(state_file):
            logger.info("No state file found")
            return
        
        try:
            with open(state_file, 'r') as f:
                serialized_state = json.load(f)
            
            # Convert string timestamps back to datetime
            for pid_str, info in serialized_state.items():
                pid = int(pid_str)
                self.tracked_processes[pid] = {
                    'cmdline': info['cmdline'],
                    'start_time': datetime.fromisoformat(info['start_time']),
                    'username': info['username'],
                    'last_checked': datetime.fromisoformat(info['last_checked']),
                    'gpu_info': info['gpu_info']
                }
            
            logger.info(f"State loaded: {len(self.tracked_processes)} processes")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
    
    def run(self, state_file="/var/lib/ml-monitor/state.json"):
        """Main monitoring loop"""
        # Load previous state if available
        self.load_state(state_file)
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, lambda signum, frame: self.stop_event.set())
        signal.signal(signal.SIGINT, lambda signum, frame: self.stop_event.set())
        
        logger.info("ML Monitor daemon started")
        
        try:
            while not self.stop_event.is_set():
                # Find new Python processes
                new_processes = self.find_python_processes()
                self.tracked_processes = new_processes
                
                # Check existing processes
                self.check_process_status()
                
                # Save current state
                self.save_state(state_file)
                
                # Sleep for the check interval
                time.sleep(self.check_interval)
        
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        
        finally:
            # Save state before exiting
            self.save_state(state_file)
            logger.info("ML Monitor daemon stopped")

def create_systemd_service():
    """Create a systemd service file for the monitor"""
    service_content = """[Unit]
Description=ML Process Monitor Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ml-monitor-daemon
Restart=on-failure
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=ml-monitor

[Install]
WantedBy=multi-user.target
"""
    
    try:
        with open('/etc/systemd/system/ml-monitor.service', 'w') as f:
            f.write(service_content)
        
        print("Systemd service file created at /etc/systemd/system/ml-monitor.service")
        print("Run the following commands to enable and start the service:")
        print("  sudo systemctl daemon-reload")
        print("  sudo systemctl enable ml-monitor")
        print("  sudo systemctl start ml-monitor")
    except Exception as e:
        print(f"Failed to create service file: {e}")
        print("You may need to run this script with sudo privileges.")

def main():
    parser = argparse.ArgumentParser(description="ML Process Monitor Daemon")
    parser.add_argument('--ntfy-server', default='ntfy.mydomain.com', 
                        help='ntfy server address (default: ntfy.mydomain.com)')
    parser.add_argument('--ntfy-topic', default='phone_only', 
                        help='ntfy topic/category (default: phone_only)')
    parser.add_argument('--check-interval', type=int, default=5,
                        help='How often to check for new/terminated processes (seconds)')
    parser.add_argument('--state-file', default='/var/lib/ml-monitor/state.json',
                        help='File to store monitor state')
    parser.add_argument('--setup-service', action='store_true',
                        help='Create systemd service file')
    
    args = parser.parse_args()
    
    if args.setup_service:
        create_systemd_service()
        return
    
    # Create data directory if it doesn't exist
    os.makedirs(os.path.dirname(args.state_file), exist_ok=True)
    
    monitor = MLMonitorDaemon(args.ntfy_server, args.ntfy_topic, args.check_interval)
    monitor.run(args.state_file)

if __name__ == "__main__":
    main()
