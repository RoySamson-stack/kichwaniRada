# backend/app/routes/mood.py
from flask import Blueprint, request, jsonify
import firebase_admin
from firebase_admin import firestore
from datetime import datetime, timedelta

mood_bp = Blueprint('mood', __name__)
db = firestore.client()

@mood_bp.route('/log', methods=['POST'])
def log_mood():
    data = request.json
    user_id = data.get('userId')
    mood_score = data.get('score')  # 1-10 scale
    mood_label = data.get('label')  # e.g., "happy", "sad", "anxious"
    notes = data.get('notes', '')
    
    if not user_id or mood_score is None:
        return jsonify({"error": "User ID and mood score are required"}), 400
    
    try:
        # Validate mood score
        mood_score = int(mood_score)
        if mood_score < 1 or mood_score > 10:
            return jsonify({"error": "Mood score must be between 1 and 10"}), 400
        
        # Store mood entry
        mood_data = {
            "score": mood_score,
            "label": mood_label,
            "notes": notes,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        mood_ref = db.collection('users').document(user_id).collection('moods')
        mood_ref.add(mood_data)
        
        # Look for patterns based on recent entries
        insights = generate_mood_insights(user_id)
        
        return jsonify({
            "success": True,
            "message": "Mood logged successfully",
            "insights": insights
        })
        
    except ValueError:
        return jsonify({"error": "Invalid mood score format"}), 400
    except Exception as e:
        print(f"Error logging mood: {e}")
        return jsonify({"error": "Failed to log mood"}), 500

@mood_bp.route('/history/<user_id>', methods=['GET'])
def get_mood_history(user_id):
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    # Get optional date range filters
    days = request.args.get('days')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    try:
        mood_ref = db.collection('users').document(user_id).collection('moods')
        
        # Apply date filters if provided
        if days:
            days = int(days)
            start_time = datetime.now() - timedelta(days=days)
            mood_ref = mood_ref.where('timestamp', '>=', start_time)
        elif start_date:
            start_time = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            mood_ref = mood_ref.where('timestamp', '>=', start_time)
            
            if end_date:
                end_time = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                mood_ref = mood_ref.where('timestamp', '<=', end_time)
        
        # Order by timestamp
        mood_ref = mood_ref.order_by('timestamp', direction='desc')
        
        # Execute query
        mood_entries = mood_ref.stream()
        
        result = []
        for entry in mood_entries:
            entry_data = entry.to_dict()
            
            # Convert Firestore timestamp to ISO format string
            timestamp = entry_data.get('timestamp')
            if timestamp:
                timestamp = timestamp.isoformat()
            
            result.append({
                "id": entry.id,
                "score": entry_data.get('score'),
                "label": entry_data.get('label'),
                "notes": entry_data.get('notes', ''),
                "timestamp": timestamp
            })
        
        # Generate summary statistics
        stats = calculate_mood_statistics(result)
        
        return jsonify({
            "entries": result,
            "statistics": stats
        })
        
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400
    except Exception as e:
        print(f"Error retrieving mood history: {e}")
        return jsonify({"error": "Failed to retrieve mood history"}), 500

def calculate_mood_statistics(mood_entries):
    """Calculate summary statistics for mood entries"""
    if not mood_entries:
        return {
            "average": None,
            "highest": None,
            "lowest": None,
            "count": 0
        }
    
    scores = [entry.get('score', 0) for entry in mood_entries]
    
    return {
        "average": sum(scores) / len(scores),
        "highest": max(scores),
        "lowest": min(scores),
        "count": len(scores)
    }

def generate_mood_insights(user_id):
    """Generate insights based on mood history"""
    try:
        # Get mood entries from the last 7 days
        seven_days_ago = datetime.now() - timedelta(days=7)
        mood_ref = db.collection('users').document(user_id).collection('moods')
        mood_ref = mood_ref.where('timestamp', '>=', seven_days_ago).order_by('timestamp')
        
        entries = list(mood_ref.stream())
        
        if len(entries) < 3:
            # Not enough data for meaningful insights
            return {
                "message": "Log more moods to receive personalized insights",
                "trends": None
            }
        
        # Extract scores and timestamps
        mood_data = []
        for entry in entries:
            entry_dict = entry.to_dict()
            mood_data.append({
                "score": entry_dict.get('score', 5),
                "timestamp": entry_dict.get('timestamp')
            })
        
        # Look for trends
        scores = [m['score'] for m in mood_data]
        avg_score = sum(scores) / len(scores)
        trend = "stable"
        
        # Check if mood is trending up or down
        if len(scores) >= 3:
            if scores[-1] > scores[0] and scores[-2] > scores[0]:
                trend = "improving"
            elif scores[-1] < scores[0] and scores[-2] < scores[0]:
                trend = "declining"
        
        # Generate relevant insight message
        if trend == "improving":
            message = "Your mood appears to be improving over the past few days."
        elif trend == "declining":
            message = "Your mood seems to be lower than usual. Consider engaging in activities that typically boost your mood."
        else:
            if avg_score >= 7:
                message = "Your mood has been consistently positive recently."
            elif avg_score <= 4:
                message = "Your mood has been lower recently. Consider reaching out for support if this continues."
            else:
                message = "Your mood has been relatively stable."
        
        return {
            "message": message,
            "trends": {
                "direction": trend,
                "average": avg_score
            }
        }
        
    except Exception as e:
        print(f"Error generating insights: {e}")
        return {
            "message": "Unable to generate insights at this time",
            "trends": None
        }