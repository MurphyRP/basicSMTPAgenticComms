# Agent-to-Agent Email Communication

This project implements a reference implementation for agent-to-agent communication over email using Gmail API, as described in the whitepaper "SMTP/IMAP as a Transport Layer for Agent-to-Agent Communication".

## Overview

This system enables AI agents to communicate with each other across organizational boundaries using standard email protocols (SMTP/IMAP) via Gmail. The implementation provides:

- Reliable message delivery with a label-based processing system
- JSON payloads embedded in email bodies for data exchange and context tracking
- Support for multiple agents running on the same machine
- Proper authentication and token management
- Message tracking using message IDs as subjects

## Prerequisites

- Python 3.7+
- A Google Cloud project with Gmail API enabled
- OAuth 2.0 credentials (downloaded as `credentials.json`)
- Two or more Gmail accounts added as test users in your OAuth consent screen

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/agent-email.git
   cd agent-email
   ```

2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your Google Cloud Project and enable Gmail API:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Navigate to "APIs & Services" > "Library"
   - Search for "Gmail API" and enable it
   - Set up the OAuth consent screen (External)
   - Add your test Gmail accounts as test users
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials as `credentials.json` and place in project root

## Running the Agents

To run the first agent:
```bash
python main.py --email agentaasdf@gmail.com
```

To run the second agent (in a separate terminal):
```bash
python main.py --email agentbasdf@gmail.com
```

Additional options:
- `--interval` or `-i`: Check interval in seconds (e.g., `--interval 30`)
- `--iterations` or `-n`: Maximum number of check iterations (e.g., `--iterations 10`)

## Initiating Agent Communication

To initiate communication between agents, you can use the included shell script:

1. First, make the script executable:
   ```bash
   chmod +x initiate_simple_exchange_demo.sh
   ```

2. Run the script with required parameters:
   ```bash
   ./initiate_simple_exchange_demo.sh --sender agentaasdf@gmail.com --target agentbasdf@gmail.com
   ```

For more options, run with the `--help` flag:
```bash
./initiate_simple_exchange_demo.sh --help
```

## JSON Message Format

Agents exchange JSON messages with the following structure:

```json
{
  "message_id": "unique_message_id", 
  "exchanges": [
    {
      "sender": "agent@example.com",
      "timestamp": "2025-04-22T18:26:58",
      "message_id": "unique_message_id",
      "recipients": ["recipient@example.com"],
      "content": {
        "action": "request",
        "message": "The actual message content",
        "expected_format": "json",
        "response_targets": ["agent@example.com"]
      }
    }
  ]
}
```

This format allows for tracking conversation history in the `exchanges` array and maintaining context between messages.

## How It Works

### Authentication Flow

1. The first time an agent runs, it needs access to the Gmail account
2. A browser window will open asking you to log in to the specific Gmail account
3. After authorization, a token is saved to a file (e.g., `agentaasdf_token.json`)
4. This token will be used for future runs without requiring manual authorization

### Message Processing

The system implements a guaranteed delivery workflow:

1. The agent checks for unread messages without the "agent-processing" label
2. Each message is marked with the "agent-processing" label
3. The agent processes the message
4. On success: message is marked as read and the processing label is removed
5. On failure: only the processing label is removed, leaving it unread for retry

This approach prevents duplicate processing while ensuring no messages are lost.

## Project Structure

- `main.py`: Entry point script
- `src/config.py`: Configuration and authentication
- `src/email_transport.py`: Email operations via Gmail API
- `src/message.py`: Message representation
- `src/agent.py`: Agent behavior implementation
- `agent_config.json`: Shared configuration file
- `initiate_simple_exchange_demo.sh`: Script for initiating agent communication

## Troubleshooting

- **Authentication Issues**: If you encounter authentication errors, delete the token files and restart the agent to go through the OAuth flow again.
- **Missing Labels**: If the "agent-processing" label doesn't exist, it will be created automatically on first run.
- **Path Issues**: Ensure all paths in the configuration file are relative to the project root.
- **Message Format**: If agents aren't communicating properly, check that the JSON payloads follow the expected format described above.