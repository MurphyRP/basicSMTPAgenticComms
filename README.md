# basicSMTPAgenticComms
Agent-to-Agent Email Communication
This project implements a reference implementation for agent-to-agent communication over email using Gmail API, as described in the whitepaper "SMTP/IMAP as a Transport Layer for Agent-to-Agent Communication".
Overview
This system enables AI agents to communicate with each other across organizational boundaries using standard email protocols (SMTP/IMAP) via Gmail. The implementation provides:

Reliable message delivery with a label-based processing system
JSON payloads embedded in email bodies
Support for multiple agents running on the same machine
Proper authentication and token management
Conversation threading via email headers

Prerequisites

Python 3.7+
A Google Cloud project with Gmail API enabled
OAuth 2.0 credentials (downloaded as credentials.json)
Two or more Gmail accounts added as test users in your OAuth consent screen

Installation

Clone this repository:

bashgit clone https://github.com/yourusername/agent-email.git
cd agent-email

Install required dependencies:

bashpip install -r requirements.txt

Set up your Google Cloud Project and enable Gmail API:

Go to the Google Cloud Console
Create a new project or select an existing one
Navigate to "APIs & Services" > "Library"
Search for "Gmail API" and enable it
Set up the OAuth consent screen (External)
Add your test Gmail accounts as test users
Create OAuth 2.0 credentials (Desktop application)
Download the credentials as credentials.json and place in project root


Create the agent_config.json file in the project root:

json{
    "description": "Shared configuration for all agents",
    "credentials_path": "credentials.json",
    "check_interval": 60,
    "max_messages": 10
}
Running the Agents
To run the first agent:
bashpython main.py --email agentaasdf@gmail.com
To run the second agent (in a separate terminal):
bashpython main.py --email agentbasdf@gmail.com
Additional options:

--interval or -i: Check interval in seconds (e.g., --interval 30)
--iterations or -n: Maximum number of check iterations (e.g., --iterations 10)

How It Works
Authentication Flow

The first time an agent runs, it needs access to the Gmail account
A browser window will open asking you to log in to the specific Gmail account
After authorization, a token is saved to a file (e.g., agentaasdf_token.json)
This token will be used for future runs without requiring manual authorization

Message Processing
The system implements a guaranteed delivery workflow:

The agent checks for unread messages without the "agent-processing" label
Each message is marked with the "agent-processing" label
The agent processes the message
On success: message is marked as read and the processing label is removed
On failure: only the processing label is removed, leaving it unread for retry

This approach prevents duplicate processing while ensuring no messages are lost.
Cross-Agent Communication
To test cross-agent communication:

Start both agents in separate terminals
Each agent will automatically reply to messages it receives
The default implementation sends acknowledgment replies

Project Structure

main.py: Entry point script
src/config.py: Configuration and authentication
src/email_transport.py: Email operations via Gmail API
src/message.py: Message representation
src/agent.py: Agent behavior implementation
agent_config.json: Shared configuration file

Extending the Agent
The base Agent class can be extended to implement custom behavior:
pythonfrom src.agent import Agent

class MyCustomAgent(Agent):
    def process_message(self, message):
        # Custom message processing logic
        print(f"Processing message from {message.sender}")
        
        # Generate a meaningful response
        response_payload = {
            "status": "processed",
            "result": "Your custom processing result here"
        }
        
        # Send the response
        self.reply_to_message(message, response_payload)
Troubleshooting

Authentication Issues: If you encounter authentication errors, delete the token files and restart the agent to go through the OAuth flow again.
Missing Labels: If the "agent-processing" label doesn't exist, it will be created automatically on first run.
Path Issues: Ensure all paths in the configuration file are relative to the project root.
