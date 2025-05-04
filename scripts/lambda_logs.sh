#!/bin/bash

# ---- Configurable Parameters ----
LAMBDA_NAME="news-digest-lambda"
REGION="us-west-2"                    # Replace with your AWS region
MINUTES_BACK=15

# ---- Derived Values ----
LOG_GROUP="/aws/lambda/$LAMBDA_NAME"
START_TIME=$(($(date +%s) - MINUTES_BACK * 60))000
END_TIME=$(date +%s)000

# ---- Fetch Log Streams ----
LOG_STREAMS=$(aws logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --order-by "LastEventTime" \
    --descending \
    --limit 1 \
    --region "$REGION" \
    --query "logStreams[*].logStreamName" \
    --output text)

# ---- Get Log Events from Each Stream ----
for stream in $LOG_STREAMS; do
    echo "---- Logs from stream: $stream ----"
    aws logs get-log-events \
        --log-group-name "$LOG_GROUP" \
        --log-stream-name "$stream" \
        --start-time "$START_TIME" \
        --end-time "$END_TIME" \
        --region "$REGION" \
        --query "events[*].{Time:timestamp,Message:message}" \
        --output text
    echo
done
