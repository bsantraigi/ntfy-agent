#!/bin/bash
# install.sh - ML Process Monitor Installation Script

set -e

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== ML Process Monitor Installation ===${NC}"

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root${NC}"
    echo "Please run: sudo ./install.sh"
    exit 1
fi

# Create directories
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p /var/lib/ml-monitor
mkdir -p /var/log/ml-monitor

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
pip3 install psutil requests || {
    echo -e "${RED}Failed to install Python dependencies${NC}"
    echo "Please make sure pip3 is installed and try again"
    exit 1
}

# Copy daemon script
echo -e "${YELLOW}Installing daemon...${NC}"
cp src/ml-monitor-daemon.py /usr/local/bin/ml-monitor-daemon
chmod +x /usr/local/bin/ml-monitor-daemon

# Copy UI script
echo -e "${YELLOW}Installing UI...${NC}"
cp src/ml-monitor-ui.py /usr/local/bin/ml-monitor-ui
chmod +x /usr/local/bin/ml-monitor-ui

# Create systemd service
echo -e "${YELLOW}Creating systemd service...${NC}"
cat > /etc/systemd/system/ml-monitor.service << EOF
[Unit]
Description=ML Process Monitor Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ml-monitor-daemon --ntfy-server ntfy.mydomain.com --ntfy-topic phone_only
Restart=on-failure
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=ml-monitor

[Install]
WantedBy=multi-user.target
EOF

# Ask if user wants to customize ntfy settings
echo -e "${YELLOW}Do you want to customize ntfy server settings? (y/N)${NC}"
read -r customize_ntfy

if [[ "$customize_ntfy" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Enter ntfy server address (default: ntfy.mydomain.com):${NC}"
    read -r ntfy_server
    ntfy_server=${ntfy_server:-ntfy.mydomain.com}
    
    echo -e "${YELLOW}Enter ntfy topic (default: phone_only):${NC}"
    read -r ntfy_topic
    ntfy_topic=${ntfy_topic:-phone_only}
    
    # Update service file with custom settings
    sed -i "s|--ntfy-server ntfy.mydomain.com|--ntfy-server $ntfy_server|g" /etc/systemd/system/ml-monitor.service
    sed -i "s|--ntfy-topic phone_only|--ntfy-topic $ntfy_topic|g" /etc/systemd/system/ml-monitor.service
fi

# Reload systemd and enable service
echo -e "${YELLOW}Enabling and starting service...${NC}"
systemctl daemon-reload
systemctl enable ml-monitor
systemctl start ml-monitor

# Create uninstall script
echo -e "${YELLOW}Creating uninstall script...${NC}"
cat > /usr/local/bin/ml-monitor-uninstall << EOF
#!/bin/bash
# Uninstall ML Process Monitor

set -e

if [ "\$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    echo "Please run: sudo ml-monitor-uninstall"
    exit 1
fi

echo "Stopping and removing service..."
systemctl stop ml-monitor || true
systemctl disable ml-monitor || true
rm -f /etc/systemd/system/ml-monitor.service
systemctl daemon-reload

echo "Removing files..."
rm -f /usr/local/bin/ml-monitor-daemon
rm -f /usr/local/bin/ml-monitor-ui
rm -f /usr/local/bin/ml-monitor-uninstall

echo "Do you want to remove all data and logs? (y/N)"
read -r remove_data
if [[ "\$remove_data" =~ ^[Yy]$ ]]; then
    rm -rf /var/lib/ml-monitor
    rm -rf /var/log/ml-monitor
    echo "Data and logs removed"
else
    echo "Data and logs preserved at /var/lib/ml-monitor and /var/log/ml-monitor"
fi

echo "ML Process Monitor has been uninstalled"
EOF

chmod +x /usr/local/bin/ml-monitor-uninstall

echo -e "${GREEN}Installation complete!${NC}"
echo -e "${YELLOW}ML Process Monitor service is now running${NC}"
echo ""
echo "You can check the service status with: sudo systemctl status ml-monitor"
echo "To view the monitor UI, run: ml-monitor-ui"
echo "To uninstall, run: sudo ml-monitor-uninstall"
echo ""
echo -e "${GREEN}Enjoy your ML Process Monitor!${NC}"
