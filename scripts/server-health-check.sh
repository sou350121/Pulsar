#!/bin/bash

# Server health check script - CRON SAFE VERSION
# Core principle: Only output when there's an actual problem, stay silent when healthy

# Exit immediately if any command fails
set -euo pipefail

# Configuration
DISK_THRESHOLD=70
MEMORY_THRESHOLD=90
MEMORY_FILE="/home/admin/clawd/memory/server-alert.json"

# Use absolute paths for all commands to avoid PATH issues in cron
DF_CMD="/bin/df"
FREE_CMD="/usr/bin/free"
PGREP_CMD="/usr/bin/pgrep"
CURL_CMD="/usr/bin/curl"

# Function to check disk usage
check_disk() {
    # Get root filesystem usage percentage (remove % sign)
    local disk_usage
    disk_usage=$($DF_CMD -h / | awk 'NR==2 {gsub(/%/,""); print $5}')
    
    # Validate it's a number
    if [[ "$disk_usage" =~ ^[0-9]+$ ]] && [ "$disk_usage" -gt "$DISK_THRESHOLD" ]; then
        echo "DISK:${disk_usage}:${DISK_THRESHOLD}"
    fi
}

# Function to check memory usage  
check_memory() {
    local memory_usage
    memory_usage=$($FREE_CMD -m | awk 'NR==2{printf "%.0f", $3*100/$2 }')
    
    # Validate it's a number
    if [[ "$memory_usage" =~ ^[0-9]+$ ]] && [ "$memory_usage" -gt "$MEMORY_THRESHOLD" ]; then
        echo "MEMORY:${memory_usage}:${MEMORY_THRESHOLD}"
    fi
}

# Function to check Moltbot Gateway process - ROBUST VERSION
check_gateway() {
    # Method 1: Check exact process name
    if $PGREP_CMD -x "moltbot-gateway" > /dev/null 2>&1; then
        return 0
    fi
    
    # Method 2: Check process with gateway in command line
    if $PGREP_CMD -f "moltbot.*gateway" > /dev/null 2>&1; then
        return 0
    fi
    
    # Method 3: Check HTTP health endpoint
    if $CURL_CMD -s --max-time 5 http://localhost:18789/health > /dev/null 2>&1; then
        return 0
    fi
    
    # All methods failed - gateway is down
    echo "GATEWAY:DOWN:UP"
}

# Main execution
main() {
    local alerts=()
    
    # Collect all alerts
    while IFS= read -r alert; do
        if [ -n "$alert" ]; then
            alerts+=("$alert")
        fi
    done < <( {
        check_disk
        check_memory
        check_gateway
    } )
    
    # If no alerts, exit silently (this is the normal case)
    if [ ${#alerts[@]} -eq 0 ]; then
        exit 0
    fi
    
    # If we have alerts, output them (this will trigger the Agent)
    for alert in "${alerts[@]}"; do
        echo "$alert"
    done
}

# Run main function
main