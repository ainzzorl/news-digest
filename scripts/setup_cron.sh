#!/bin/bash

# Script to setup cron job for news-digest
# Runs daily at 11AM with logs stored in workspace/logs
# Usage: ./setup_cron.sh [--test]
#   --test: Creates a one-time test job that runs 2 minutes from now

# Get workspace directory (parent of scripts directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOGS_DIR="$WORKSPACE_DIR/logs"

# Find poetry executable
POETRY_PATH=$(which poetry)
if [ -z "$POETRY_PATH" ]; then
    echo "Error: poetry not found in PATH"
    echo "Please ensure poetry is installed and in your PATH"
    exit 1
fi

echo "Found poetry at: $POETRY_PATH"
PYTHON_CMD="$POETRY_PATH run python scripts/main.py --gen --upload --mail --output local/digest.html"

# Check for --test flag
TEST_MODE=false
if [ "$1" == "--test" ]; then
    TEST_MODE=true
    # Calculate time 2 minutes from now
    FUTURE_TIME=$(date -d "+2 minutes" "+%M %H %d %m")
    MINUTE=$(echo $FUTURE_TIME | awk '{print $1}')
    HOUR=$(echo $FUTURE_TIME | awk '{print $2}')
    DAY=$(echo $FUTURE_TIME | awk '{print $3}')
    MONTH=$(echo $FUTURE_TIME | awk '{print $4}')
    CRON_TIME="$MINUTE $HOUR $DAY $MONTH *"
    echo "TEST MODE: Will run once at $(date -d "+2 minutes" "+%Y-%m-%d %H:%M:%S")"
else
    CRON_TIME="0 11 * * *"
fi

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
if [ "$TEST_MODE" == "true" ]; then
    echo "  - Schedule: ONE-TIME TEST at $(date -d "+2 minutes" "+%Y-%m-%d %H:%M")"
    echo "  - This job will run ONCE and then you should run this script again without --test"
else
    echo "  - Schedule: Daily at 11:00 AM"
fi
echo "  - Logs directory: $LOGS_DIR"
echo "  - Log file pattern: digest_YYYY-MM-DD.log"

if [ "$TEST_MODE" == "true" ]; then
    echo ""
    echo "To monitor the test run:"
    echo "  tail -f $LOGS_DIR/digest_\$(date +%Y-%m-%d).log"
    echo ""
    echo "After the test completes, remove the test job and setup the daily job:"
    echo "  ./scripts/setup_cron.sh"
fi

