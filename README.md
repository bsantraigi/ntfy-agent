# ML Process Monitor

A comprehensive monitoring tool for ML training/inference jobs on headless cloud servers. This tool automatically monitors Python processes and sends notifications when they finish or crash.

## Features

- **Background Daemon**: Automatically monitors all Python processes on the system
- **Interactive Terminal UI**: htop/btop-like interface for real-time monitoring
- **Notifications**: Sends alerts via ntfy when processes finish
- **GPU Monitoring**: Tracks GPU usage for ML processes
- **User-Friendly**: No need to modify how users start their experiments

## Installation

1. Clone the repository:
```bash
git clone https://github.com/bsantraigi/ntfy-agent.git
cd ntfy-agent
```

2. Run the installation script (requires root privileges):
```bash
sudo ./install.sh
```

The installation script will:
- Install required dependencies
- Set up the daemon and UI scripts
- Create a systemd service for background monitoring
- Allow customization of notification settings
- Provide an uninstall script

## Usage

### Terminal UI

Run the terminal UI to view all monitored processes:

```bash
ml-monitor-ui
```

**UI Controls:**
- **q**: Quit
- **s**: Toggle sort criteria (CPU, Memory, Time, GPU)
- **r**: Toggle sort direction (ascending/descending)
- **a**: Toggle showing all processes (including terminated ones)
- **F5**: Refresh

### Notification Configuration

The monitor sends notifications to your ntfy server. You can customize the server and topic during installation.

Default configuration:
- Server: ntfy.mydomain.com
- Topic: phone_only

To change settings after installation, edit the systemd service file:
```bash
sudo systemctl edit ml-monitor
```

### Checking Service Status

```bash
# View service status
sudo systemctl status ml-monitor

# Check logs
sudo journalctl -u ml-monitor
```

## Architecture

The system consists of two main components:

1. **Background Daemon** (`ml-monitor-daemon`):
   - Runs as a systemd service
   - Detects Python processes automatically
   - Tracks process lifecycle
   - Sends notifications when processes complete
   - Maintains state between restarts

2. **Terminal UI** (`ml-monitor-ui`):
   - Provides interactive monitoring interface
   - Shows CPU, memory, and GPU usage
   - Displays process runtime and user information
   - Allows sorting and filtering of processes

## Uninstalling

To completely remove ML Process Monitor:

```bash
sudo ml-monitor-uninstall
```

This will:
- Stop and remove the systemd service
- Remove all installed scripts
- Optionally remove all data and logs

## Troubleshooting

### Common Issues

1. **No processes showing in UI:**
   - Check if the daemon is running: `sudo systemctl status ml-monitor`
   - Verify state file exists: `ls -l /var/lib/ml-monitor/state.json`

2. **Not receiving notifications:**
   - Verify ntfy server settings in systemd service
   - Check network connectivity to ntfy server
   - Check the daemon logs for errors: `sudo journalctl -u ml-monitor`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
