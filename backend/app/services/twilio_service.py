# backend/app/services/twilio_service.py
from twilio.rest import Client
import os
from flask import Flask, request, jsonify, Blueprint
from app.services.openai_service import OpenAIService
import firebase_admin
from firebase_admin import firestore

class TwilioService:
    def __init__(self):
        self.account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.phone_number = os.environ.get('TWILIO_PHONE_NUMBER')
        self.whatsapp_number = f"whatsapp:{self.phone_number}" if self.phone_number else None
        self.client = Client(self.account_sid, self.auth_token) if self.account_sid and self.auth_token else None
        self.openai_service = OpenAIService()
        self.db = firestore.client()
        
    def send_sms(self, to_number, message):
        """Send an SMS message via Twilio
        
        Args:
            to_number: Recipient's phone number
            message: Message content
            
        Returns:
            Success status
        """
        if not self.client:
            print("Twilio client not initialized")
            return False
            
        try:
            message = self.client.messages.create(
                body=message,
                from_=self.phone_number,
                to=to_number
            )
            
            return True
        except Exception as e:
            print(f"Error sending SMS: {e}")
            return False
            
    def send_whatsapp(self, to_number, message):
        """Send a WhatsApp message via Twilio
        
        Args:
            to_number: Recipient's phone number (without 'whatsapp:' prefix)
            message: Message content
            
        Returns:
            Success status
        """
        if not self.client or not self.whatsapp_number:
            print("Twilio WhatsApp not configured")
            return False
            
        # Format the recipient's number for WhatsApp
        to_whatsapp = f"whatsapp:{to_number}"
        
        try:
            message = self.client.messages.create(
                body=message,
                from_=self.whatsapp_number,
                to=to_whatsapp
            )
            
            return True
        except Exception as e:
            print(f"Error sending WhatsApp message: {e}")
            return False
    
    def process_incoming_message(self, from_number, body, message_type="sms"):
        """Process an incoming message from SMS or WhatsApp
        
        Args:
            from_number: Sender's phone number
            body: Message content
            message_type: 'sms' or 'whatsapp'
            
        Returns:
            Response message
        """
        try:
            # Find or create user based on phone number
            user_id = self._get_user_id_from_phone(from_number)
            
            if not user_id:
                # Create new user profile for this phone number
                user_id = self._create_user_for_phone(from_number)
            
            # Get chat history for context
            chat_history = []
            chat_ref = self.db.collection('chats').document(user_id)
            messages_ref = chat_ref.collection('messages').order_by('timestamp', direction='asc').limit(10).stream()
            
            for msg in messages_ref:
                msg_data = msg.to_dict()
                chat_history.append({
                    "sender": msg_data.get('sender'),
                    "content": msg_data.get('content')
                })
            
            # Store incoming message
            message_data = {
                "sender": "user",
                "content": body,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "channel": message_type
            }
            
            chat_ref.collection('messages').add(message_data)
            
            # Get AI response
            ai_response = self.openai_service.get_chat_response(body, chat_history)
            
            # Check for crisis indicators
            crisis_assessment = self.openai_service.assess_crisis_risk(body)
            high_risk = crisis_assessment.get('crisis_risk', 0) >= 7
            
            # Append crisis resources for high risk messages
            if high_risk:
                crisis_type = crisis_assessment.get('crisis_type')
                if crisis_type == "suicidal" or crisis_type == "self_harm":
                    ai_response += "\n\nImportant: If you're having thoughts of harming yourself, please contact the National Suicide Prevention Lifeline at 988 or 1-800-273-8255."
                else:
                    ai_response += "\n\nResources: If you need immediate support, consider contacting a crisis helpline like 988 (National Suicide Prevention Lifeline)."
            
            # Store AI response
            response_data = {
                "sender": "bot",
                "content": ai_response,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "channel": message_type
            }
            
            chat_ref.collection('messages').add(response_data)
            
            return ai_response
            
        except Exception as e:
            print(f"Error processing incoming message: {e}")
            return "I'm having trouble processing your message right now. Please try again later."
    
    def _get_user_id_from_phone(self, phone_number):
        """Find user ID associated with a phone number"""
        try:
            # Clean the phone number
            clean_number = phone_number.replace('whatsapp:', '')
            
            # Query users by phone number
            users_ref = self.db.collection('users').where('phoneNumber', '==', clean_number).limit(1).stream()
            
            for user in users_ref:
                return user.id
                
            return None
            
        except Exception as e:
            print(f"Error finding user by phone: {e}")
            return None
    
    def _create_user_for_phone(self, phone_number):
        """Create a new user for an unrecognized phone number"""
        try:
            # Clean the phone number
            clean_number = phone_number.replace('whatsapp:', '')
            
            # Create user document
            user_data = {
                'phoneNumber': clean_number,
                'channel': 'sms' if 'whatsapp:' not in phone_number else 'whatsapp',
                'created': firestore.SERVER_TIMESTAMP,
                'lastInteraction': firestore.SERVER_TIMESTAMP,
                'displayName': f"User-{clean_number[-4:]}"  # Last 4 digits as name
            }
            
            # Add user to Firestore
            user_ref = self.db.collection('users').document()
            user_ref.set(user_data)
            
            # Create default settings
            settings_ref = self.db.collection('userSettings').document(user_ref.id)
            settings_ref.set({
                'notifications': True,
                'moodTrackingEnabled': True
            })
            
            return user_ref.id
            
        except Exception as e:
            print(f"Error creating user for phone: {e}")
            # Generate a temporary ID as fallback
            import uuid
            return f"temp-{uuid.uuid4()}"


# Create a Blueprint for the Twilio webhook routes
twilio_bp = Blueprint('twilio', __name__)
twilio_service = TwilioService()

@twilio_bp.route('/sms/webhook', methods=['POST'])
def sms_webhook():
    """Handle incoming SMS messages from Twilio"""
    from_number = request.values.get('From', '')
    body = request.values.get('Body', '')
    
    if not from_number or not body:
        return "Invalid request", 400
    
    # Process the incoming message
    response = twilio_service.process_incoming_message(from_number, body, "sms")
    
    # Return TwiML response
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>{response}</Message>
    </Response>
    """
    
    return twiml_response, 200, {'Content-Type': 'text/xml'}

@twilio_bp.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages from Twilio"""
    from_number = request.values.get('From', '')
    body = request.values.get('Body', '')
    
    if not from_number or not body:
        return "Invalid request", 400
    
    # Process the incoming message
    response = twilio_service.process_incoming_message(from_number, body, "whatsapp")
    
    # Return TwiML response
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>{response}</Message>
    </Response>
    """
    
    return twiml_response, 200, {'Content-Type': 'text/xml'}