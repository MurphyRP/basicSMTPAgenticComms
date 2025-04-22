#!/bin/bash

# Script to initiate a simple agent-to-agent exchange
# This script calls the agent's main.py with appropriate parameters to start a conversation

echo "Starting agent-to-agent exchange demo script..."

# Display help information
show_help() {
    echo "Usage: $0 --sender <sender_email> --target <target_email> [options]"
    echo
    echo "Options:"
    echo "  --sender, -s       Email address of the sending agent (required)"
    echo "  --target, -t       Email address of the target agent (required)"
    echo "  --message, -m      Message content (default: 'Hello, this is a test message')"
    echo "  --action, -a       Action type (default: 'request')"
    echo "  --format, -f       Expected response format (default: 'json')"
    echo "  --interval, -i     Check interval in seconds (use config default if not specified)"
    echo "  --iterations, -n   Number of message check iterations (default: 1)"
    echo "  --help, -h         Show this help message"
    echo
    echo "Example:"
    echo "  $0 --sender agent1@example.com --target agent2@example.com --message 'Process this data'"
    exit 1
}

# Default values
MESSAGE="Hello, this is a test message"
ACTION="request"
FORMAT="json"
ITERATIONS="1"  # Default to just one check to avoid long-running script

echo "Processing command line arguments..."

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --sender|-s)
            SENDER="$2"
            echo "Sender: $SENDER"
            shift 2
            ;;
        --target|-t)
            TARGET="$2"
            echo "Target: $TARGET"
            shift 2
            ;;
        --message|-m)
            MESSAGE="$2"
            echo "Message: $MESSAGE"
            shift 2
            ;;
        --action|-a)
            ACTION="$2"
            echo "Action: $ACTION"
            shift 2
            ;;
        --format|-f)
            FORMAT="$2"
            echo "Format: $FORMAT"
            shift 2
            ;;
        --interval|-i)
            INTERVAL="$2"
            echo "Interval: $INTERVAL"
            shift 2
            ;;
        --iterations|-n)
            ITERATIONS="$2"
            echo "Iterations: $ITERATIONS"
            shift 2
            ;;
        --help|-h)
            show_help
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            ;;
    esac
done

# Check for required arguments
if [ -z "$SENDER" ] || [ -z "$TARGET" ]; then
    echo "Error: Sender and target emails are required."
    show_help
fi

# Construct interval argument if provided
INTERVAL_ARG=""
if [ ! -z "$INTERVAL" ]; then
    INTERVAL_ARG="--interval $INTERVAL"
    echo "Using interval argument: $INTERVAL_ARG"
fi

# Escape special characters in the message
ESCAPED_MESSAGE=$(echo "$MESSAGE" | sed 's/"/\\"/g')
echo "Escaped message: $ESCAPED_MESSAGE"

# Execute the agent with appropriate parameters
echo "Initiating message from $SENDER to $TARGET..."
echo "Message: $MESSAGE"
echo "Action: $ACTION"
echo "Expected format: $FORMAT"

# Create a JSON payload for our message
TIMESTAMP=$(date +%s)
echo "Using timestamp: $TIMESTAMP"

PAYLOAD="{
    \"message_id\": \"$TIMESTAMP\",
    \"exchanges\": [
        {
            \"sender\": \"$SENDER\",
            \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\",
            \"message_id\": \"$TIMESTAMP\",
            \"recipients\": [\"$TARGET\"],
            \"content\": {
                \"action\": \"$ACTION\",
                \"message\": \"$ESCAPED_MESSAGE\",
                \"expected_format\": \"$FORMAT\",
                \"response_targets\": [\"$SENDER\"]
            }
        }
    ]
}"

echo "Generated payload:"
echo "$PAYLOAD"

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "Error: main.py not found in the current directory."
    echo "Please run this script from the project root directory."
    exit 1
fi

echo "Running main.py..."

# Run the agent to send the message and check for responses
python main.py --email "$SENDER" --target "$TARGET" --message "$PAYLOAD" \
    --iterations "$ITERATIONS" $INTERVAL_ARG

echo "Demo complete. Check for messages in the agent's inbox."