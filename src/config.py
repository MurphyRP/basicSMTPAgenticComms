"""
Configuration module for Gmail API authentication and environment management.

This module handles the OAuth 2.0 authentication process required to interact with Gmail API.
The authentication flow works as follows:

1. The first time an agent runs, it needs access to your Gmail account.
2. The authenticate() method will open a browser window asking you to log in to the 
   specific Gmail account (e.g., agentaasdf@gmail.com) and grant permission.
3. After you authorize access, Google provides a token that gets saved to a file
   specific to this agent (e.g., agentaasdf_token.json).
4. For future runs, the saved token will be used automatically without requiring
   manual authorization, unless the token expires or is revoked.

Each agent email address will have its own token file, allowing multiple agents
to operate independently on the same machine while using the same application credentials.

Prerequisites:
- A Google Cloud project with Gmail API enabled
- OAuth 2.0 client credentials (credentials.json file) downloaded from Google Cloud Console
- The appropriate Gmail account(s) added as test users in your OAuth consent screen
"""

import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Gmail API scope for modifying emails
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

class Config:
    """Configuration management for Gmail agent communication."""
    
    def __init__(self, agent_email=None):
        """Initialize the configuration.
        
        Args:
            agent_email: Full email address of the agent (e.g., 'agentaasdf@gmail.com')
        """
        # Get agent email from parameter or environment variable
        self.agent_email = agent_email or os.environ.get('AGENT_EMAIL')
        
        if not self.agent_email:
            raise ValueError("Agent email not provided in arguments or environment variables")
        
        # Extract agent name from email (part before @)
        self.agent_name = self.agent_email.split('@')[0]
        print(f"Initializing configuration for agent: {self.agent_name}")
        
        # Load shared configuration file
        config_path = "agent_config.json"  # Config is in the project root
        self.config = self.load_json_config(config_path)
        
        # Get credentials path only from config or environment variable
        self.credentials_path = self.config.get('credentials_path') or os.environ.get('CREDENTIALS_PATH')
        
        if not self.credentials_path:
            raise ValueError("Credentials path not specified in config file or environment variables")
        
        # Agent-specific token path
        token_base = "token.json"
        self.token_path = f"{self.agent_name}_{token_base}"
        
        print(f"Agent configuration: {self.agent_name}, Email: {self.agent_email}")
        print(f"Using credentials: {self.credentials_path}, Token: {self.token_path}")
    
    def authenticate(self):
        """Authenticate with the Gmail API for this agent.
        
        Returns:
            A Gmail API service instance
        """
        creds = None
        
        # Check if token file exists for this agent
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        # If credentials don't exist or are invalid, refresh or get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                print(f"Please authorize access for {self.agent_email}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                
            # Save the credentials for future runs
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
                print(f"Saved authentication token to {self.token_path}")
        
        # Build and return the Gmail API service
        return build('gmail', 'v1', credentials=creds)
    
    @staticmethod
    def load_json_config(config_path):
        """Load configuration from a JSON file.
        
        Args:
            config_path: Path to the JSON configuration file
            
        Returns:
            Dictionary containing the configuration values
        """
        try:
            with open(config_path, 'r') as file:
                config = json.load(file)
                print(f"Loaded configuration from {config_path}")
                return config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load config file {config_path}: {e}")
            print(f"Using default configuration settings")
            return {}
        
    def get_check_interval(self):
        """Get the check interval for polling messages.
        
        Returns:
            Check interval in seconds (default: 60)
        """
        return self.config.get('check_interval', 60)
    
    def get_max_messages(self):
        """Get the maximum number of messages to process per check.
        
        Returns:
            Maximum number of messages (default: 10)
        """
        return self.config.get('max_messages', 10)