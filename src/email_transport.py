"""
EmailTransport module for handling interactions with the Gmail API.

This module provides a class that encapsulates all Gmail API operations required for agent communication,
including sending messages, retrieving messages, and managing message state.

The EmailTransport class implements a label-based approach for guaranteed message processing,
preventing concurrent processing while allowing for retries of failed operations.
"""

import base64
import json
from email.mime.text import MIMEText
from googleapiclient.errors import HttpError
from message import Message

# Label used to mark messages being processed
PROCESSING_LABEL = "agent-processing"

class EmailTransport:
    """Handles email transportation via Gmail API."""
    
    def __init__(self, gmail_service, agent_email):
        """Initialize the transport with a Gmail API service.
        
        Args:
            gmail_service: An authenticated Gmail API service instance
            agent_email: The email address of this agent
        """
        self.service = gmail_service
        self.agent_email = agent_email
        self._ensure_processing_label_exists()
        print(f"Initialized EmailTransport for {agent_email}")
    
    def _ensure_processing_label_exists(self):
        """Ensure the processing label exists in the Gmail account."""
        try:
            # Get all labels
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            
            # Check if our processing label exists
            for label in labels:
                if label['name'] == PROCESSING_LABEL:
                    return
            
            # Create the label if it doesn't exist
            label_object = {
                'name': PROCESSING_LABEL,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }
            self.service.users().labels().create(userId='me', body=label_object).execute()
            print(f"Created label '{PROCESSING_LABEL}'")
            
        except HttpError as error:
            print(f"Error ensuring processing label exists: {error}")
    
    def send_message(self, message):
        """Send a Message object.
        
        Args:
            message: A Message object to send
            
        Returns:
            Updated Message object with ID and thread ID from Gmail
        """
        try:
            # Ensure the message has the correct sender
            if not message.sender:
                message.sender = self.agent_email
                
            # Create email message
            mime_message = self._create_mime_message(message)
            body = {'raw': base64.urlsafe_b64encode(mime_message.as_bytes()).decode()}
            
            # Add thread ID if continuing a conversation
            if message.thread_id:
                body['threadId'] = message.thread_id
            
            # Send the message
            sent_message = self.service.users().messages().send(
                userId='me', body=body).execute()
            
            # Update the message with the ID and thread ID from Gmail
            message.message_id = sent_message['id']
            message.thread_id = sent_message['threadId']
            
            print(f"Message sent: ID={message.message_id}, threadId={message.thread_id}")
            
            return message
            
        except HttpError as error:
            print(f"Error sending message: {error}")
            return None
    
    def get_unread_messages(self, max_results=10):
        """Get unread messages that are not being processed.
        
        Args:
            max_results: Maximum number of messages to retrieve
            
        Returns:
            List of Message objects with the processing label already applied
        """
        try:
            # Search for unread messages not being processed
            query = f"is:unread -label:{PROCESSING_LABEL}"
            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=max_results).execute()
            
            message_refs = results.get('messages', [])
            
            if not message_refs:
                print("No unread messages found.")
                return []
            
            # Get full message details for each message reference
            messages = []
            for msg_ref in message_refs:
                # Mark as processing before retrieving full content
                self.mark_as_processing(msg_ref['id'])
                
                # Get the full message
                message = self.get_message(msg_ref['id'])
                if message:
                    messages.append(message)
                else:
                    # If message retrieval failed, mark as processing failed
                    self.mark_as_processing_failed(msg_ref['id'])
            
            print(f"Retrieved {len(messages)} unread messages")
            return messages
            
        except HttpError as error:
            print(f"Error retrieving messages: {error}")
            return []
    
    def get_message(self, message_id):
        """Get a specific message by ID.
        
        Args:
            message_id: The ID of the message to retrieve
            
        Returns:
            A Message object, or None if not found
        """
        try:
            # Get the message from Gmail API
            gmail_message = self.service.users().messages().get(
                userId='me', id=message_id).execute()
            
            # Extract headers
            headers = {}
            if 'payload' in gmail_message and 'headers' in gmail_message['payload']:
                for header in gmail_message['payload']['headers']:
                    headers[header['name'].lower()] = header['value']
            
            # Extract references from headers
            references = []
            if 'references' in headers:
                references = headers['references'].split()
            
            # Extract the message body
            raw_payload = self._get_message_body(gmail_message)
            payload = None
            
            if raw_payload:
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    print(f"Message {message_id} does not contain valid JSON")
                    payload = None
            
            # Create a Message object
            message = Message(
                sender=headers.get('from'),
                recipient=headers.get('to'),
                subject=headers.get('subject', ''),
                payload=payload,
                message_id=gmail_message['id'],
                thread_id=gmail_message['threadId'],
                references=references,
                date=headers.get('date')
            )
            
            return message
            
        except HttpError as error:
            print(f"Error retrieving message {message_id}: {error}")
            return None
    
    def mark_as_processing(self, message):
        """Mark a message as being processed by adding the processing label.
        
        Args:
            message: A Message object or message ID string
            
        Returns:
            True if successful, False otherwise
        """
        # Extract message_id if a Message object was passed
        message_id = message.message_id if isinstance(message, Message) else message
            
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [self._get_label_id(PROCESSING_LABEL)]}
            ).execute()
            
            print(f"Marked message {message_id} as processing")
            return True
            
        except HttpError as error:
            print(f"Error marking message as processing: {error}")
            return False
    
    def mark_as_processing_succeeded(self, message):
        """Mark a message as successfully processed by removing the processing label and UNREAD label.
        
        This is called when message processing has completed successfully.
        
        Args:
            message: A Message object or message ID string
            
        Returns:
            True if successful, False otherwise
        """
        # Extract message_id if a Message object was passed
        message_id = message.message_id if isinstance(message, Message) else message
            
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD', self._get_label_id(PROCESSING_LABEL)]}
            ).execute()
            
            print(f"Marked message {message_id} as successfully processed (read)")
            return True
            
        except HttpError as error:
            print(f"Error marking message as processed: {error}")
            return False
    
    def mark_as_processing_failed(self, message):
        """Mark a message as failed processing by removing the processing label but keeping UNREAD label.
        
        This is called when message processing has failed and should be retried later.
        
        Args:
            message: A Message object or message ID string
            
        Returns:
            True if successful, False otherwise
        """
        # Extract message_id if a Message object was passed
        message_id = message.message_id if isinstance(message, Message) else message
            
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': [self._get_label_id(PROCESSING_LABEL)]}
            ).execute()
            
            print(f"Marked message {message_id} as failed processing (still unread)")
            return True
            
        except HttpError as error:
            print(f"Error marking message as failed: {error}")
            return False
    
    def _get_label_id(self, label_name):
        """Get the ID for a label by name.
        
        Args:
            label_name: Name of the label
            
        Returns:
            The label ID, or the label name if the label isn't found
        """
        try:
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            
            for label in labels:
                if label['name'] == label_name:
                    return label['id']
            
            # If label not found, return the name (which works in some cases)
            return label_name
            
        except HttpError as error:
            print(f"Error getting label ID: {error}")
            return label_name
    
    def _create_mime_message(self, message):
        """Create an email MIME message from a Message object.
        
        Args:
            message: A Message object
            
        Returns:
            An email.mime.text.MIMEText object
        """
        # Convert payload to JSON string with pretty formatting
        json_content = json.dumps(message.payload, indent=2)
        
        # Create MIME message
        mime_message = MIMEText(json_content)
        mime_message['to'] = message.recipient
        mime_message['from'] = message.sender
        mime_message['subject'] = message.subject
        
        # Add references and in-reply-to headers if applicable
        if message.references and len(message.references) > 0:
            mime_message['References'] = ' '.join(message.references)
            mime_message['In-Reply-To'] = message.references[-1]
        
        return mime_message
    
    def _get_message_body(self, gmail_message):
        """Extract the body content from a Gmail API message object.
        
        Args:
            gmail_message: A Gmail API message object
            
        Returns:
            The decoded message body as a string, or None if not found
        """
        if not gmail_message:
            return None
            
        # Check if the message has parts (multipart email)
        if 'parts' in gmail_message['payload']:
            for part in gmail_message['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                    return base64.urlsafe_b64decode(
                        part['body']['data']).decode('utf-8')
        
        # Otherwise, check for body data in the main payload
        elif 'body' in gmail_message['payload'] and 'data' in gmail_message['payload']['body']:
            return base64.urlsafe_b64decode(
                gmail_message['payload']['body']['data']).decode('utf-8')
        
        return None