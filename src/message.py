"""
Message module for representing agent communication messages.

This module provides a class that encapsulates the structure of messages exchanged between
agents, including metadata and JSON payload. The Message class provides methods for creating
new messages, creating replies to existing messages, and serializing/deserializing messages
to/from JSON format.

The Message class is designed to work with the EmailTransport class, providing a clean
separation between message representation and transport mechanics.
"""

import json
import datetime
import uuid

class Message:
    """Represents a message exchanged between agents."""
    
    def __init__(self, sender=None, recipient=None, subject=None, payload=None, 
                 message_id=None, thread_id=None, references=None, date=None):
        """Initialize a new message.
        
        Args:
            sender: Email address of the message sender
            recipient: Email address of the message recipient
            subject: Subject line of the message
            payload: Dictionary containing the JSON payload
            message_id: Unique identifier for the message (generated if None)
            thread_id: Thread identifier for conversation grouping
            references: List of message IDs that this message references
            date: Timestamp of the message (current time if None)
        """
        self.sender = sender
        self.recipient = recipient
        self.subject = subject
        self.payload = payload or {}
        self.message_id = message_id or str(uuid.uuid4())
        self.thread_id = thread_id
        self.references = references or []
        self.date = date or datetime.datetime.now().isoformat()
        
    @classmethod
    def from_transport_response(cls, response_dict):
        """Create a Message object from an EmailTransport response dictionary.
        
        Args:
            response_dict: Dictionary from EmailTransport.get_message()
            
        Returns:
            A new Message object
        """
        if not response_dict:
            return None
            
        return cls(
            sender=response_dict.get('sender'),
            recipient=response_dict.get('recipient'),
            subject=response_dict.get('subject'),
            payload=response_dict.get('payload'),
            message_id=response_dict.get('id'),
            thread_id=response_dict.get('threadId'),
            references=response_dict.get('references', []),
            date=response_dict.get('date')
        )
    
    def create_reply(self, reply_payload):
        """Create a new Message object as a reply to this message.
        
        Args:
            reply_payload: Dictionary containing the JSON payload for the reply
            
        Returns:
            A new Message object configured as a reply
        """
        # Swap sender and recipient
        sender = self.recipient
        recipient = self.sender
        
        # Use message_id as subject (removing "Re:" functionality)
        subject = self.message_id
        
        # Create references list with this message's ID
        references = self.references.copy()
        if self.message_id not in references:
            references.append(self.message_id)
        
        # Create the reply message
        return Message(
            sender=sender,
            recipient=recipient,
            subject=subject,
            payload=reply_payload,
            thread_id=self.thread_id,
            references=references
        )
    
    def to_dict(self):
        """Convert the message to a dictionary.
        
        Returns:
            Dictionary representation of the message
        """
        return {
            'message_id': self.message_id,
            'thread_id': self.thread_id,
            'sender': self.sender,
            'recipient': self.recipient,
            'subject': self.subject,
            'date': self.date,
            'references': self.references,
            'payload': self.payload
        }
    
    def to_json(self):
        """Convert the message to a JSON string.
        
        Returns:
            JSON string representation of the message
        """
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str):
        """Create a Message object from a JSON string.
        
        Args:
            json_str: JSON string representation of a message
            
        Returns:
            A new Message object
        """
        try:
            data = json.loads(json_str)
            return cls(
                sender=data.get('sender'),
                recipient=data.get('recipient'),
                subject=data.get('subject'),
                payload=data.get('payload'),
                message_id=data.get('message_id'),
                thread_id=data.get('thread_id'),
                references=data.get('references', []),
                date=data.get('date')
            )
        except json.JSONDecodeError as e:
            print(f"Error decoding message JSON: {e}")
            return None
    
    def is_reply(self):
        """Check if this message is a reply to another message.
        
        Returns:
            True if this is a reply, False otherwise
        """
        return len(self.references) > 0
    
    def __str__(self):
        """Return a string representation of the message.
        
        Returns:
            String representation with key message details
        """
        return f"Message(id={self.message_id}, subject='{self.subject}', " \
               f"sender='{self.sender}', recipient='{self.recipient}')"