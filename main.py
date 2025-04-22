"""
Main script for running an agent.

This script creates and runs an agent using the specified email address.
It handles command-line arguments and initializes the required components.
"""

import argparse
import time
import sys
from src.config import Config
from src.email_transport import EmailTransport
from src.agent import Agent  

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run an email agent')
    parser.add_argument('--email', '-e', required=True, 
                      help='Full email address of the agent (e.g., agentaasdf@gmail.com)')
    parser.add_argument('--interval', '-i', type=int, default=60,
                      help='Check interval in seconds (default: 60)')
    parser.add_argument('--iterations', '-n', type=int, default=None,
                      help='Maximum number of iterations (default: run indefinitely)')
    
    args = parser.parse_args()
    
    try:
        # Initialize configuration
        config = Config(agent_email=args.email)
        
        # Authenticate and create transport
        gmail_service = config.authenticate()
        transport = EmailTransport(gmail_service, config.agent_email)
        
        # Create and run agent
        agent = Agent(transport, config.agent_email, check_interval=args.interval)
        agent.run(max_iterations=args.iterations)
        
    except KeyboardInterrupt:
        print("\nAgent stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()