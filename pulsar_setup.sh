#!/bin/bash

# Pulsar One-click Deploy Script
# Interactive setup.sh for guided deployment
# Compatible with Linux (Ubuntu/Debian/RHEL) and macOS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command_exists lsb_release; then
            DISTRO=$(lsb_release -is)
        elif [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO=$NAME
        else
            DISTRO="Linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        DISTRO="macOS"
    else
        DISTRO="Unknown"
    fi
    echo "$DISTRO"
}

# Function to get current user home directory
get_user_home() {
    echo "$HOME"
}

# Function to validate API key format
validate_api_key() {
    local key="$1"
    if [[ -z "$key" ]] || [[ ${#key} -lt 10 ]]; then
        return 1
    fi
    return 0
}

# Function to validate GitHub token format
validate_github_token() {
    local token="$1"
    if [[ -z "$token" ]] || [[ ! "$token" =~ ^[a-zA-Z0-9_]+$ ]]; then
        return 1
    fi
    return 0
}

# Function to validate Telegram token format
validate_telegram_token() {
    local token="$1"
    if [[ -z "$token" ]] || [[ ! "$token" =~ ^[0-9]+:[a-zA-Z0-9_-]+$ ]]; then
        return 1
    fi
    return 0
}

# Function to validate domain name
validate_domain() {
    local domain="$1"
    if [[ -z "$domain" ]] || [[ ! "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$ ]]; then
        return 1
    fi
    return 0
}

# Main setup function
main() {
    print_info "Welcome to Pulsar One-click Deploy Script!"
    print_info "This script will guide you through the setup process."
    echo
    
    # Detect OS
    OS=$(detect_os)
    print_info "Detected OS: $OS"
    
    # Get user home directory
    USER_HOME=$(get_user_home)
    print_info "User home directory: $USER_HOME"
    
    # Create Pulsar directory if it doesn't exist
    PULSAR_DIR="$USER_HOME/pulsar"
    if [ ! -d "$PULSAR_DIR" ]; then
        mkdir -p "$PULSAR_DIR"
        print_info "Created Pulsar directory: $PULSAR_DIR"
    fi
    
    # Change to Pulsar directory
    cd "$PULSAR_DIR"
    
    # Configuration variables
    LLM_PROVIDER=""
    LLM_API_KEY=""
    GITHUB_TOKEN=""
    GITHUB_REPO=""
    TELEGRAM_BOT_TOKEN=""
    TELEGRAM_CHAT_ID=""
    DOMAIN_NAME=""
    RSS_FEEDS=""
    
    # Prompt for LLM Provider and API Key
    echo
    print_info "=== LLM Configuration ==="
    while true; do
        read -p "Enter LLM provider (openai, anthropic, etc.): " LLM_PROVIDER
        if [[ -n "$LLM_PROVIDER" ]]; then
            break
        fi
        print_warning "LLM provider cannot be empty."
    done
    
    while true; do
        read -s -p "Enter LLM API key: " LLM_API_KEY
        echo
        if validate_api_key "$LLM_API_KEY"; then
            break
        fi
        print_warning "Invalid API key format. Please try again."
    done
    
    # Prompt for GitHub configuration
    echo
    print_info "=== GitHub Configuration ==="
    while true; do
        read -s -p "Enter GitHub personal access token: " GITHUB_TOKEN
        echo
        if validate_github_token "$GITHUB_TOKEN"; then
            break
        fi
        print_warning "Invalid GitHub token format. Please try again."
    done
    
    while true; do
        read -p "Enter target repository (username/repo): " GITHUB_REPO
        if [[ -n "$GITHUB_REPO" ]] && [[ "$GITHUB_REPO" == */* ]]; then
            break
        fi
        print_warning "Invalid repository format. Please use username/repo format."
    done
    
    # Prompt for Telegram configuration
    echo
    print_info "=== Telegram Configuration ==="
    while true; do
        read -s -p "Enter Telegram bot token (123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ): " TELEGRAM_BOT_TOKEN
        echo
        if validate_telegram_token "$TELEGRAM_BOT_TOKEN"; then
            break
        fi
        print_warning "Invalid Telegram token format. Please try again."
    done
    
    while true; do
        read -p "Enter Telegram chat ID: " TELEGRAM_CHAT_ID
        if [[ -n "$TELEGRAM_CHAT_ID" ]] && [[ "$TELEGRAM_CHAT_ID" =~ ^-?[0-9]+$ ]]; then
            break
        fi
        print_warning "Invalid chat ID format. Please enter a numeric chat ID."
    done
    
    # Prompt for domain and RSS feeds
    echo
    print_info "=== Domain and RSS Configuration ==="
    while true; do
        read -p "Enter domain name (example.com): " DOMAIN_NAME
        if validate_domain "$DOMAIN_NAME"; then
            break
        fi
        print_warning "Invalid domain name format. Please try again."
    done
    
    read -p "Enter RSS feeds (comma-separated URLs, optional): " RSS_FEEDS
    
    # Create .env file from template
    print_info "Creating .env file..."
    cat > .env << EOF
# LLM Configuration
LLM_PROVIDER=$LLM_PROVIDER
LLM_API_KEY=$LLM_API_KEY

# GitHub Configuration
GITHUB_TOKEN=$GITHUB_TOKEN
GITHUB_REPO=$GITHUB_REPO

# Telegram Configuration
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID

# Domain Configuration
DOMAIN_NAME=$DOMAIN_NAME

# RSS Configuration
RSS_FEEDS=$RSS_FEEDS
EOF
    
    # Create active-config.json from template
    print_info "Creating active-config.json..."
    cat > active-config.json << EOF
{
  "llm": {
    "provider": "$LLM_PROVIDER",
    "api_key": "$LLM_API_KEY"
  },
  "github": {
    "token": "$GITHUB_TOKEN",
    "repo": "$GITHUB_REPO"
  },
  "telegram": {
    "bot_token": "$TELEGRAM_BOT_TOKEN",
    "chat_id": "$TELEGRAM_CHAT_ID"
  },
  "domain": "$DOMAIN_NAME",
  "rss_feeds": $(if [[ -n "$RSS_FEEDS" ]]; then echo "[\"$(echo "$RSS_FEEDS" | sed 's/,/","/g')\"]"; else echo "[]"; fi)
}
EOF
    
    # Replace path placeholders
    print_info "Replacing path placeholders..."
    sed -i "s|/home/admin|$USER_HOME|g" .env active-config.json 2>/dev/null || true
    
    # Create cron job
    print_info "Setting up cron jobs..."
    CRON_JOB="0 * * * * cd $PULSAR_DIR && ./gateway.sh"
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    
    # Start gateway service
    print_info "Starting gateway service..."
    if [ -f "gateway.sh" ]; then
        chmod +x gateway.sh
        nohup ./gateway.sh > gateway.log 2>&1 &
        print_info "Gateway service started in background."
    else
        print_warning "gateway.sh not found. Please ensure Pulsar is properly cloned."
    fi
    
    # Print verification steps
    echo
    print_info "=== Setup Complete! ==="
    print_info "Verification steps:"
    print_info "1. Check .env file: cat $PULSAR_DIR/.env"
    print_info "2. Check active-config.json: cat $PULSAR_DIR/active-config.json"
    print_info "3. Check cron jobs: crontab -l"
    print_info "4. Check gateway logs: tail -f $PULSAR_DIR/gateway.log"
    print_info "5. Test deployment by accessing your domain: https://$DOMAIN_NAME"
    
    echo
    print_info "Thank you for using Pulsar One-click Deploy Script!"
    print_info "If you encounter any issues, please report them to the Pulsar repository."
}

# Run main function
main