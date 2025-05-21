# backend/app/services/openai_service.py
import openai
import os
from typing import List, Dict, Any

class OpenAIService:
    def __init__(self):
        openai.api_key = os.environ.get('OPENAI_API_KEY')
        self.system_prompt = """
You are a supportive mental health chatbot designed to provide empathetic 
responses and helpful guidance. You are not a replacement for professional 
mental health services, and you should always recommend seeking professional 
help for serious concerns. Focus on active listening, validation, and 
providing evidence-based coping strategies when appropriate. Never diagnose 
medical conditions or provide medical advice. If a user appears to be in 
crisis or expresses suicidal thoughts, direct them to appropriate crisis 
resources.
"""

    def get_chat_response(self, message: str, chat_history: List[Dict[str, str]] = None) -> str:
        """
        Get a response from OpenAI's GPT model for mental health support
        
        Args:
            message: The user's message
            chat_history: Previous messages in the conversation
            
        Returns:
            The AI's response
        """
        if chat_history is None:
            chat_history = []
            
        # Prepare messages for API
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add chat history
        for msg in chat_history[-10:]:  # Limit context to last 10 messages
            messages.append({"role": "user" if msg["sender"] == "user" else "assistant", 
                           "content": msg["content"]})
            
        # Add current message
        messages.append({"role": "user", "content": message})
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",  # Using GPT-4 for better understanding and responses
                messages=messages,
                temperature=0.7,  # Slightly creative but still focused
                max_tokens=500,  # Limit response length
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0.6  # Slight penalty for repetition
            )
            
            return response.choices[0].message["content"].strip()
            
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return "I'm having trouble connecting right now. Please try again in a moment."
            
    def assess_crisis_risk(self, message: str) -> Dict[str, Any]:
        """
        Analyze message for potential crisis indicators
        
        Args:
            message: The user's message
            
        Returns:
            Dict with risk assessment
        """
        try:
            messages = [
                {"role": "system", "content": """
Analyze the following message for indicators of mental health crisis. 
Provide a JSON response with the following fields:
- crisis_risk: number between 0-10 (0 being no risk, 10 being severe)
- crisis_type: string (suicidal, self_harm, panic, other, none)
- recommended_action: string (emergency_services, crisis_line, professional_help, self_care, monitor)
Do not include any explanations, just the JSON object.
"""},
                {"role": "user", "content": message}
            ]
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=messages,
                temperature=0,  # No creativity for risk assessment
                max_tokens=150,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
            )
            
            response_text = response.choices[0].message["content"].strip()
            
            import json
            try:
                result = json.loads(response_text)
                return result
            except json.JSONDecodeError:
                # Fallback if response isn't valid JSON
                return {
                    "crisis_risk": 0,
                    "crisis_type": "none",
                    "recommended_action": "monitor"
                }
                
        except Exception as e:
            print(f"Error in crisis assessment: {e}")
            # Default safe response
            return {
                "crisis_risk": 5,  # Moderate risk as fallback
                "crisis_type": "other",
                "recommended_action": "crisis_line"
            }