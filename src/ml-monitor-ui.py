#!/usr/bin/env python3
import os
import sys
import time
import json
import curses
import argparse
import psutil
from datetime import datetime, timedelta

class MLMonitorUI:
    def __init__(self, state_file="/var/lib/ml-monitor/state.json"):
        self.state_file = state_file
        self.tracked_processes = {}
        self.live_processes = {}
        self.sort_by = "cpu"  # Options: cpu, memory, time, gpu
        self.sort_reverse = True
        self.show_all = False  # Show terminated processes
    
    def load_daemon_state(self):
        """Load the daemon's saved state"""
        if not os.path.exists(self.state_file):
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                serialized_state = json.load(f)
            
            state = {}
            # Convert string timestamps back to datetime
            for pid_str, info in serialized_state.items():
                pid = int(pid_str)
                state[pid] = {
                    'cmdline': info['cmdline'],
                    'start_time': datetime.fromisoformat(info['start_time']),
                    'username': info['username'],
                    'last_checked': datetime.fromisoformat(info['last_checked']),
                    'gpu_info': info['gpu_info']
                }
            
            return state
        except Exception as e:
            return {}
    
    def get_process_stats(self, pid):
        """Get current stats for a running process"""
        try:
            proc = psutil.Process(pid)
            stats = {
                'cpu_percent': proc.cpu_percent(interval=0.1),
                'memory_percent': proc.memory_percent(),
                'status': proc.status(),
                'running': True
            }
            
            # Try to get GPU info from nvidia-smi
            try:
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-compute-apps=pid,used_memory,utilization.gpu', '--format=csv,noheader'],
                    capture_output=True, text=True
                )
                
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if not line.strip():
                            continue
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 2 and parts[0] == str(pid):
                            stats['gpu_memory'] = parts[1] if len(parts) > 1 else 'N/A'
                            stats['gpu_util'] = parts[2] if len(parts) > 2 else 'N/A'
            except Exception:
                pass
                
            return stats
        except psutil.NoSuchProcess:
            return {'running': False, 'status': 'terminated'}
    
    def update_process_list(self):
        """Update the list of monitored processes"""
        # Load processes from daemon state file
        daemon_state = self.load_daemon_state()
        self.tracked_processes = daemon_state
        
        # Update stats for each tracked process
        for pid in list(self.tracked_processes.keys()):
            # Check if process is still running and get stats
            stats = self.get_process_stats(pid)
            self.tracked_processes[pid].update(stats)
            
            # Remove terminated processes if not showing all
            if not stats['running'] and not self.show_all:
                del self.tracked_processes[pid]
    
    def sort_processes(self):
        """Sort processes based on current sort criteria"""
        processes = list(self.tracked_processes.items())
        
        if self.sort_by == "cpu":
            processes.sort(key=lambda x: x[1].get('cpu_percent', 0), reverse=self.sort_reverse)
        elif self.sort_by == "memory":
            processes.sort(key=lambda x: x[1].get('memory_percent', 0), reverse=self.sort_reverse)
        elif self.sort_by == "time":
            processes.sort(key=lambda x: x[1]['start_time'], reverse=self.sort_reverse)
        elif self.sort_by == "gpu":
            # Try to sort by GPU memory if available
            def get_gpu_mem(proc):
                gpu_info = proc[1].get('gpu_memory', '')
                if isinstance(gpu_info, str) and 'MiB' in gpu_info:
                    try:
                        return float(gpu_info.replace('MiB', '').strip())
                    except ValueError:
                        pass
                return 0
            processes.sort(key=get_gpu_mem, reverse=self.sort_reverse)
        
        return processes
    
    def format_duration(self, start_time):
        """Format duration from start time to now"""
        duration = datetime.now() - start_time
        days = duration.days
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def run(self, stdscr):
        """Main UI loop"""
        # Setup colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)
        curses.init_pair(6, curses.COLOR_BLUE, -1)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Header
        
        # Hide cursor
        curses.curs_set(0)
        
        # Enable keypad mode
        stdscr.keypad(True)
        
        # Set non-blocking input
        stdscr.timeout(1000)  # Update every second
        
        while True:
            # Get terminal size
            height, width = stdscr.getmaxyx()
            
            # Update process list
            self.update_process_list()
            
            # Sort processes
            sorted_processes = self.sort_processes()
            
            # Clear screen
            stdscr.clear()
            
            # Draw header
            header = " ML Process Monitor "
            sub_header = f" Processes: {len(sorted_processes)} | Sort: {self.sort_by} | {'↓' if self.sort_reverse else '↑'} | Show All: {'Yes' if self.show_all else 'No'} "
            
            stdscr.addstr(0, (width - len(header)) // 2, header, curses.color_pair(7) | curses.A_BOLD)
            stdscr.addstr(1, (width - len(sub_header)) // 2, sub_header)
            
            # Column headers
            col_headers = " PID | USER | CPU% | MEM% | GPU | RUNTIME | COMMAND "
            stdscr.addstr(3, 0, col_headers, curses.A_BOLD)
            stdscr.addstr(4, 0, "─" * (width - 1))
            
            # Draw processes
            max_rows = height - 8  # Leave room for header and footer
            displayed_procs = sorted_processes[:max_rows]
            
            row = 5
            for pid, info in displayed_procs:
                # Skip if we're out of space
                if row >= height - 3:
                    break
                
                # Format each field
                status = info.get('status', 'unknown')
                running = info.get('running', False)
                
                # Choose color based on status
                color = curses.color_pair(1)  # Green for running
                if not running:
                    color = curses.color_pair(3)  # Red for terminated
                elif status == 'sleeping':
                    color = curses.color_pair(2)  # Yellow for sleeping
                
                # Format GPU info if available
                gpu_info = "N/A"
                if 'gpu_memory' in info and info['gpu_memory']:
                    gpu_info = info['gpu_memory']
                
                # Format runtime
                runtime = self.format_duration(info['start_time'])
                
                # Format command (truncate if needed)
                cmd = info['cmdline']
                username = info['username']
                cmd_space = width - 45  # Adjust based on other columns
                if len(cmd) > cmd_space:
                    cmd = cmd[:cmd_space-3] + "..."
                
                # Format line
                line = f" {pid:5} | {username[:8]:8} | {info.get('cpu_percent', 0):4.1f} | {info.get('memory_percent', 0):4.1f} | {gpu_info:8} | {runtime:8} | {cmd}"
                
                # Display the line
                stdscr.addstr(row, 0, line, color)
                row += 1
            
            # Show help text at the bottom
            help_text = " q: Quit | s: Toggle Sort | r: Toggle Sort Direction | a: Toggle Show All | F5: Refresh "
            stdscr.addstr(height-2, 0, "─" * (width - 1))
            stdscr.addstr(height-1, 0, help_text)
            
            # Update screen
            stdscr.refresh()
            
            # Handle input
            try:
                key = stdscr.getch()
                
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    # Cycle through sort options
                    sort_options = ["cpu", "memory", "time", "gpu"]
                    current_idx = sort_options.index(self.sort_by)
                    self.sort_by = sort_options[(current_idx + 1) % len(sort_options)]
                elif key == ord('r'):
                    # Toggle sort direction
                    self.sort_reverse = not self.sort_reverse
                elif key == ord('a'):
                    # Toggle showing all processes
                    self.show_all = not self.show_all
                elif key == curses.KEY_F5:
                    # Force refresh
                    pass
            except KeyboardInterrupt:
                break

def main():
    parser = argparse.ArgumentParser(description="ML Process Monitor UI")
    parser.add_argument('--state-file', default='/var/lib/ml-monitor/state.json',
                       help='Path to the daemon state file')
    
    args = parser.parse_args()
    
    ui = MLMonitorUI(args.state_file)
    
    try:
        curses.wrapper(ui.run)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
