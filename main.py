"""
Main script for running an agent.

This script creates and runs an agent using the specified email address.
It handles command-line arguments and initializes the required components.
"""

import argparse
import time
import json
import sys
from src.config import Config
from src.email_transport import EmailTransport
from src.agent import Agent  

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run an email agent')
    parser.add_argument('--email', '-e', required=True, 
                      help='Full email address of the agent (e.g., agentaasdf@gmail.com)')
    parser.add_argument('--interval', '-i', type=int,
                      help='Check interval in seconds (overrides config file)')
    parser.add_argument('--iterations', '-n', type=int, default=None,
                      help='Maximum number of iterations (default: run indefinitely)')
    
    # Options for initiating communication
    init_group = parser.add_argument_group('Communication initiation options')
    init_group.add_argument('--target', '-t', 
                      help='Target agent email address to initiate communication with')
    init_group.add_argument('--message', '-m',
                      help='Message payload (as JSON string) to send if target is specified')
    
    args = parser.parse_args()
    
    try:
        # Initialize configuration
        config = Config(agent_email=args.email)
        
        # Authenticate and create transport
        gmail_service = config.authenticate()
        max_messages = config.get_max_messages()
        transport = EmailTransport(gmail_service, config.agent_email, max_messages=max_messages)
        
        # Create agent - use config file values with command line arguments as overrides
        check_interval = args.interval if args.interval is not None else config.get_check_interval()
        agent = Agent(transport, config.agent_email, check_interval=check_interval)
        
        # Send initial message if target specified
        if args.target:
            if not args.message:
                print("Error: If --target is specified, --message must also be provided")
                sys.exit(1)
                
            try:
                # Parse message content as JSON
                try:
                    payload = json.loads(args.message)
                except json.JSONDecodeError as e:
                    print(f"Error: Message payload must be valid JSON: {e}")
                    sys.exit(1)
                
                # Use message_id as subject for cross-message referencing
                subject = str(payload.get("message_id", time.time()))
                
                # Send the message
                print(f"Sending initial message to {args.target}...")
                print(f"Content: {json.dumps(payload, indent=2)}")
                sent = agent.send_message(args.target, subject, payload)
                if sent:
                    print(f"Successfully sent initial message: {sent}")
                    print(f"Message ID: {sent.message_id}")
                else:
                    print("Failed to send initial message")
                    
            except Exception as e:
                print(f"Error sending initial message: {e}")
                sys.exit(1)
        
        # Run the agent
        agent.run(max_iterations=args.iterations)
        
    except KeyboardInterrupt:
        print("\nAgent stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()