"""
Agent module for implementing agent behavior.

This module provides a base Agent class that handles the core functionality needed for
agent-to-agent communication, including checking for messages, processing incoming messages,
and sending responses.

The Agent class implements a robust message processing workflow with guaranteed delivery:
1. Check for unread messages without the "agent-processing" label
2. For each message, mark it as processing
3. Process the message
4. On success, mark as processed successfully (read + no processing label)
5. On failure, mark as processing failed (unread + no processing label)

This class is designed to be extended for specific agent implementations with custom behavior.
"""

import time
import traceback
from .message import Message

class Agent:
    """Base class for implementing agent behavior."""
    
    def __init__(self, email_transport, agent_email, check_interval=60):
        """Initialize the agent.
        
        Args:
            email_transport: An EmailTransport instance for communication
            agent_email: The email address of this agent
            check_interval: How often to check for new messages (in seconds)
        """
        self.transport = email_transport
        self.agent_email = agent_email
        self.check_interval = check_interval
        print(f"Initialized Agent with email {agent_email}")
    
    def send_message(self, to_email, subject, payload):
        """Send a message to another agent.
        
        Args:
            to_email: Email address of the recipient
            subject: Subject line of the message
            payload: Dictionary containing the JSON payload
            
        Returns:
            The sent Message object with updated IDs, or None if sending failed
        """
        # Create a new message
        message = Message(
            sender=self.agent_email,
            recipient=to_email,
            subject=subject,
            payload=payload
        )
        
        # Send the message using the transport
        return self.transport.send_message(message)
    
    def reply_to_message(self, original_message, reply_payload):
        """Reply to a message.
        
        Args:
            original_message: The Message object to reply to
            reply_payload: Dictionary containing the JSON payload for the reply
            
        Returns:
            The sent Message object with updated IDs, or None if sending failed
        """
        # Create a reply message
        reply = original_message.create_reply(reply_payload)
        
        # Send the reply using the transport
        return self.transport.send_message(reply)
    
    def check_for_messages(self):
        """Check for new unread messages and process them.
        
        Returns:
            The number of messages processed
        """
        # Get unread messages
        # Note: EmailTransport.get_unread_messages already marks them as processing
        messages = self.transport.get_unread_messages()
        
        # Process each message
        processed_count = 0
        for message in messages:
            try:
                # Process the message
                print(f"Processing message: {message}")
                self.process_message(message)
                
                # Mark as processing succeeded if processing completed without errors
                self.transport.mark_as_processing_succeeded(message)
                processed_count += 1
                
            except Exception as e:
                # Log the error and mark the message as processing failed
                print(f"Error processing message {message.message_id}: {str(e)}")
                print(traceback.format_exc())
                self.transport.mark_as_processing_failed(message)
        
        return processed_count
    
    def process_message(self, message):
        """Process an incoming message.
        
        This method should be overridden by subclasses to implement specific behavior.
        The base implementation just logs the message and sends a simple acknowledgment.
        
        Args:
            message: A Message object to process
        """
        print(f"Received message from {message.sender}: {message.subject}")
        print(f"Payload: {message.payload}")
        
        # Create response using our JSON schema
        reply_payload = {
            "message_id": message.message_id,
            "exchanges": []
        }
        
        # If message has existing exchanges, copy them
        if isinstance(message.payload, dict) and "exchanges" in message.payload:
            reply_payload["exchanges"] = message.payload["exchanges"].copy()
        
        # Add new exchange entry
        new_exchange = {
            "sender": self.agent_email,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "message_id": message.message_id,
            "recipients": [message.sender],
            "content": {
                "action": "acknowledge",
                "message": f"Your message was received by {self.agent_email}",
                "expected_format": "json",
                "response_targets": [message.sender]
            }
        }
        
        # Add our response to the exchanges
        reply_payload["exchanges"].append(new_exchange)
        
        # Send a simple acknowledgment reply
        self.reply_to_message(message, reply_payload)
    
    def run(self, max_iterations=None):
        """Run the agent's main loop.
        
        Args:
            max_iterations: Maximum number of check iterations (None for infinite)
        """
        iteration = 0
        try:
            while max_iterations is None or iteration < max_iterations:
                print(f"Agent {self.agent_email} checking for messages...")
                count = self.check_for_messages()
                print(f"Processed {count} messages")
                
                iteration += 1
                if max_iterations is None or iteration < max_iterations:
                    print(f"Sleeping for {self.check_interval} seconds...")
                    time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("Agent stopped by user")
        
        print(f"Agent {self.agent_email} finished running")