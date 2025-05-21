# backend/app/routes/chat.py
from flask import Blueprint, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
from datetime import datetime
from app.services.openai_service import OpenAIService

chat_bp = Blueprint('chat', __name__)
openai_service = OpenAIService()

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    cred_path = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
    else:
        # For development, we might use a JSON string from environment variable
        cred_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
        if cred_json:
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
        else:
            raise ValueError("Firebase credentials not found")
            
    firebase_admin.initialize_app(cred)

db = firestore.client()

@chat_bp.route('/send', methods=['POST'])
def send_message():
    data = request.json
    user_id = data.get('userId')
    message = data.get('message')
    
    if not user_id or not message:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Get chat history for context
    chat_history = []
    try:
        chat_ref = db.collection('chats').document(user_id)
        messages_ref = chat_ref.collection('messages').order_by('timestamp', direction='asc').limit(10)
        messages = messages_ref.stream()
        
        for msg in messages:
            msg_data = msg.to_dict()
            chat_history.append({
                "sender": msg_data.get('sender'),
                "content": msg_data.get('content')
            })
    except Exception as e:
        print(f"Error retrieving chat history: {e}")
    
    # Store user message
    try:
        message_data = {
            "sender": "user",
            "content": message,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        chat_ref = db.collection('chats').document(user_id)
        chat_ref.collection('messages').add(message_data)
    except Exception as e:
        print(f"Error storing user message: {e}")
    
    # Check for crisis indicators in the message
    crisis_assessment = openai_service.assess_crisis_risk(message)
    high_risk = crisis_assessment.get('crisis_risk', 0) >= 7
    
    # Get AI response
    ai_response = openai_service.get_chat_response(message, chat_history)
    
    # Append crisis resources if high risk is detected
    if high_risk:
        crisis_type = crisis_assessment.get('crisis_type')
        if crisis_type == "suicidal" or crisis_type == "self_harm":
            ai_response += "\n\n**Important**: If you're having thoughts of harming yourself, please contact the National Suicide Prevention Lifeline at 988 or 1-800-273-8255, or text HOME to 741741 to reach the Crisis Text Line."
        else:
            ai_response += "\n\n**Resources**: If you need immediate support, consider contacting a crisis helpline like 988 (National Suicide Prevention Lifeline) or texting HOME to 741741 (Crisis Text Line)."
    
    # Store AI response
    try:
        response_data = {
            "sender": "bot",
            "content": ai_response,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        chat_ref.collection('messages').add(response_data)
    except Exception as e:
        print(f"Error storing AI response: {e}")
    
    return jsonify({
        "response": ai_response,
        "crisis_assessment": crisis_assessment
    })

@chat_bp.route('/history/<user_id>', methods=['GET'])
def get_chat_history(user_id):
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    try:
        # Get chat messages
        chat_ref = db.collection('chats').document(user_id)
        messages_ref = chat_ref.collection('messages').order_by('timestamp', direction='asc')
        messages = messages_ref.stream()
        
        chat_history = []
        for msg in messages:
            msg_data = msg.to_dict()
            # Convert Firestore timestamp to ISO format string
            timestamp = msg_data.get('timestamp')
            if timestamp:
                timestamp = timestamp.isoformat()
            
            chat_history.append({
                "id": msg.id,
                "sender": msg_data.get('sender'),
                "content": msg_data.get('content'),
                "timestamp": timestamp
            })
        
        return jsonify({"history": chat_history})
    
    except Exception as e:
        print(f"Error retrieving chat history: {e}")
        return jsonify({"error": "Failed to retrieve chat history"}), 500

@chat_bp.route('/clear/<user_id>', methods=['DELETE'])
def clear_chat_history(user_id):
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    try:
        # Delete all messages in the chat
        chat_ref = db.collection('chats').document(user_id)
        messages_ref = chat_ref.collection('messages')
        
        # Firestore doesn't support deleting collections directly
        # We need to retrieve all documents and delete them
        batch_size = 100
        docs = messages_ref.limit(batch_size).stream()
        deleted = 0
        
        for doc in docs:
            doc.reference.delete()
            deleted += 1
            
        return jsonify({"success": True, "deleted": deleted})
    
    except Exception as e:
        print(f"Error clearing chat history: {e}")
        return jsonify({"error": "Failed to clear chat history"}), 500