#!/bin/bash

# Script to setup cron job for news-digest
# Runs daily at 11AM with logs stored in workspace/logs

# Get workspace directory (parent of scripts directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOGS_DIR="$WORKSPACE_DIR/logs"
PYTHON_CMD="python scripts/main.py --gen --upload --mail --output local/digest.html"
CRON_TIME="0 11 * * *"

# Create logs directory if it doesn't exist
echo "Creating logs directory at: $LOGS_DIR"
mkdir -p "$LOGS_DIR"

# Build the cron job command with logging
LOG_FILE="$LOGS_DIR/digest_\$(date +\%Y-\%m-\%d).log"
CRON_CMD="cd $WORKSPACE_DIR && $PYTHON_CMD >> $LOG_FILE 2>&1"
CRON_JOB="$CRON_TIME $CRON_CMD"

# Check if cron job already exists
echo "Checking existing crontab..."
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -F "scripts/main.py --gen --upload --mail" || true)

if [ -n "$EXISTING_CRON" ]; then
    echo "Found existing cron job:"
    echo "  $EXISTING_CRON"
    read -p "Remove existing job and add new one? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Remove old job and add new one
        (crontab -l 2>/dev/null | grep -vF "scripts/main.py --gen --upload --mail"; echo "$CRON_JOB") | crontab -
        echo "Updated cron job!"
    else
        echo "Keeping existing cron job. Exiting."
        exit 0
    fi
else
    # Add new cron job
    echo "Adding new cron job..."
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job added successfully!"
fi

echo ""
echo "Current crontab:"
crontab -l | grep -F "scripts/main.py" || echo "  (no matching jobs found)"

echo ""
echo "Setup complete!"
echo "  - Command: $PYTHON_CMD"
echo "  - Schedule: Daily at 11:00 AM"
echo "  - Logs directory: $LOGS_DIR"
echo "  - Log file pattern: digest_YYYY-MM-DD.log"

