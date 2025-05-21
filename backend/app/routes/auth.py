# backend/app/routes/auth.py
from flask import Blueprint, request, jsonify
import firebase_admin
from firebase_admin import auth, firestore
import json
from datetime import datetime

auth_bp = Blueprint('auth', __name__)
db = firestore.client()

@auth_bp.route('/register', methods=['POST'])
def register_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    display_name = data.get('displayName')
    
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    
    try:
        # Create user in Firebase Authentication
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name or email
        )
        
        # Store additional user info in Firestore
        user_ref = db.collection('users').document(user.uid)
        user_ref.set({
            'email': email,
            'displayName': display_name or email,
            'created': firestore.SERVER_TIMESTAMP,
            'lastLogin': firestore.SERVER_TIMESTAMP
        })
        
        # Create initial user settings
        settings_ref = db.collection('userSettings').document(user.uid)
        settings_ref.set({
            'notifications': True,
            'theme': 'light',
            'moodTrackingEnabled': True,
            'goalReminders': False
        })
        
        # Create custom token for frontend auth
        custom_token = auth.create_custom_token(user.uid)
        
        return jsonify({
            "message": "User registered successfully",
            "userId": user.uid,
            "token": custom_token.decode('utf-8')
        })
        
    except Exception as e:
        print(f"Error registering user: {e}")
        error_message = str(e)
        if "EMAIL_EXISTS" in error_message:
            return jsonify({"error": "Email already in use"}), 400
        else:
            return jsonify({"error": "Failed to register user"}), 500

@auth_bp.route('/verify-token', methods=['POST'])
def verify_token():
    data = request.json
    id_token = data.get('idToken')
    
    if not id_token:
        return jsonify({"error": "ID token is required"}), 400
    
    try:
        # Verify the ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        # Update last login timestamp
        user_ref = db.collection('users').document(uid)
        user_ref.update({
            'lastLogin': firestore.SERVER_TIMESTAMP
        })
        
        return jsonify({
            "userId": uid,
            "email": decoded_token.get('email'),
            "verified": True
        })
        
    except Exception as e:
        print(f"Error verifying token: {e}")
        return jsonify({"error": "Invalid token", "verified": False}), 401

@auth_bp.route('/user/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    try:
        # Get user data from Firestore
        user_ref = db.collection('users').document(user_id)
        user_data = user_ref.get()
        
        if not user_data.exists:
            return jsonify({"error": "User not found"}), 404
        
        user_info = user_data.to_dict()
        
        # Get user settings
        settings_ref = db.collection('userSettings').document(user_id)
        settings_data = settings_ref.get()
        
        settings = {}
        if settings_data.exists:
            settings = settings_data.to_dict()
        
        # Remove sensitive information
        if 'passwordHash' in user_info:
            del user_info['passwordHash']
        
        return jsonify({
            "profile": user_info,
            "settings": settings
        })
        
    except Exception as e:
        print(f"Error retrieving user profile: {e}")
        return jsonify({"error": "Failed to retrieve user profile"}), 500

@auth_bp.route('/settings/<user_id>', methods=['PUT'])
def update_user_settings(user_id):
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    data = request.json
    
    try:
        # Update user settings
        settings_ref = db.collection('userSettings').document(user_id)
        settings_ref.update(data)
        
        return jsonify({
            "success": True,
            "message": "Settings updated successfully"
        })
        
    except Exception as e:
        print(f"Error updating user settings: {e}")
        return jsonify({"error": "Failed to update settings"}), 500