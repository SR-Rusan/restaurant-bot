from flask import Flask, request
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from keep_alive import keep_alive
import logging

logging.basicConfig(level=logging.INFO)

# ============================================================
# CONFIG — EDIT THIS SECTION FOR EACH CLIENT
# ============================================================
CONFIG = {
    "restaurant_name": "Demo Bistro",
    "google_review_link": "https://maps.google.com/demo",
    "owner_number": "880XXXXXXXXXX",   # with country code, no +
    "ultramsg_token": "YOUR_TOKEN",
    "instance_id": "YOUR_INSTANCE_ID",
    "followup_hours": 24,              # hours before follow-up sent
}
# ============================================================

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# In-memory storage
# Structure: { phone: { "state": "", "rating": 0, "lang": "", "name": "" } }
user_data = {}

# ============ LANGUAGE DETECTION ============
def detect_language(text):
    bengali_chars = set('অআইঈউঊঋএঐওঔকখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহড়ঢ়য়ৎংঃঁ')
    for char in text:
        if char in bengali_chars:
            return 'bn'
    return 'en'

# ============ MESSAGES ============
def get_messages(lang, name=""):
    first_name = name.split()[0] if name else "there"

    messages = {
        'en': {
            'welcome': (
                f"👋 Hi {first_name}! Thank you for visiting "
                f"{CONFIG['restaurant_name']}!\n\n"
                f"How was your experience today?\n\n"
                f"Please reply with a number:\n\n"
                f"1️⃣ Very Poor\n"
                f"2️⃣ Poor\n"
                f"3️⃣ Average\n"
                f"4️⃣ Good\n"
                f"5️⃣ Excellent"
            ),
            'invalid_rating': (
                "Please reply with a number between 1 and 5 only 😊"
            ),
            'positive': (
                f"🌟 Thank you so much!\n\n"
                f"We're thrilled you enjoyed your visit to "
                f"{CONFIG['restaurant_name']}.\n\n"
                f"Would you mind leaving us a quick Google review?\n"
                f"It only takes 30 seconds and means the world to us:\n\n"
                f"👉 {CONFIG['google_review_link']}\n\n"
                f"See you again soon! 🙏"
            ),
            'negative': (
                f"We're really sorry about your experience. 😔\n\n"
                f"Could you please tell us what went wrong?\n\n"
                f"Your message goes directly to our manager and "
                f"we will personally make it right."
            ),
            'complaint_received': (
                f"Thank you for letting us know. 🙏\n\n"
                f"Your feedback has been sent directly to our manager "
                f"at {CONFIG['restaurant_name']}.\n\n"
                f"We take every complaint seriously and will look "
                f"into this immediately.\n\n"
                f"We hope to make it up to you on your next visit! 😊"
            ),
            'followup': (
                f"Hi {first_name}! 👋\n\n"
                f"This is a quick follow-up from "
                f"{CONFIG['restaurant_name']}.\n\n"
                f"Did you get a chance to leave us a Google review? "
                f"It really helps us grow:\n\n"
                f"👉 {CONFIG['google_review_link']}\n\n"
                f"Thank you so much! 🙏"
            ),
            'already_reviewed': (
                f"That's wonderful, thank you! 🌟\n\n"
                f"See you at {CONFIG['restaurant_name']} again soon!"
            ),
            'fallback': (
                f"Hi! 👋 Send *hi* or *hello* to rate your experience "
                f"at {CONFIG['restaurant_name']}!"
            ),
        },
        'bn': {
            'welcome': (
                f"👋 হ্যালো {first_name}! {CONFIG['restaurant_name']}-এ "
                f"আসার জন্য ধন্যবাদ!\n\n"
                f"আজকের অভিজ্ঞতা কেমন ছিল?\n\n"
                f"একটি নম্বর দিয়ে উত্তর দিন:\n\n"
                f"1️⃣ খুব খারাপ\n"
                f"2️⃣ খারাপ\n"
                f"3️⃣ মোটামুটি\n"
                f"4️⃣ ভালো\n"
                f"5️⃣ অসাধারণ"
            ),
            'invalid_rating': (
                "অনুগ্রহ করে শুধুমাত্র ১ থেকে ৫ এর মধ্যে একটি নম্বর দিন 😊"
            ),
            'positive': (
                f"🌟 অনেক ধন্যবাদ!\n\n"
                f"{CONFIG['restaurant_name']}-এ আপনার ভালো অভিজ্ঞতা "
                f"হয়েছে জেনে আমরা খুশি।\n\n"
                f"আপনি কি আমাদের একটি Google রিভিউ দিতে পারবেন?\n"
                f"মাত্র ৩০ সেকেন্ড লাগবে:\n\n"
                f"👉 {CONFIG['google_review_link']}\n\n"
                f"আবার আসবেন! 🙏"
            ),
            'negative': (
                f"আপনার অভিজ্ঞতা ভালো হয়নি জেনে আমরা সত্যিই দুঃখিত। 😔\n\n"
                f"কী সমস্যা হয়েছিল একটু বলবেন কি?\n\n"
                f"আপনার বার্তা সরাসরি আমাদের ম্যানেজারের কাছে যাবে "
                f"এবং আমরা বিষয়টি সমাধান করব।"
            ),
            'complaint_received': (
                f"জানানোর জন্য ধন্যবাদ। 🙏\n\n"
                f"আপনার অভিযোগ {CONFIG['restaurant_name']}-এর ম্যানেজারের "
                f"কাছে পাঠানো হয়েছে।\n\n"
                f"আমরা এটি গুরুত্বের সাথে নেব এবং দ্রুত সমাধান করব।\n\n"
                f"আশা করি পরের বার আরও ভালো অভিজ্ঞতা দিতে পারব! 😊"
            ),
            'followup': (
                f"হ্যালো {first_name}! 👋\n\n"
                f"{CONFIG['restaurant_name']} থেকে একটি ফলো-আপ বার্তা।\n\n"
                f"আপনি কি আমাদের Google রিভিউ দিতে পেরেছেন?\n\n"
                f"👉 {CONFIG['google_review_link']}\n\n"
                f"আপনার সহযোগিতার জন্য অনেক ধন্যবাদ! 🙏"
            ),
            'already_reviewed': (
                f"অসংখ্য ধন্যবাদ! 🌟\n\n"
                f"{CONFIG['restaurant_name']}-এ আবার আসবেন!"
            ),
            'fallback': (
                f"হ্যালো! 👋 {CONFIG['restaurant_name']}-এ আপনার অভিজ্ঞতা "
                f"জানাতে *hi* বা *হ্যালো* লিখুন!"
            ),
        }
    }
    return messages[lang]

# ============ SEND WHATSAPP ============
def send_whatsapp(to, message):
    url = (
        f"https://api.ultramsg.com/"
        f"{CONFIG['instance_id']}/messages/chat"
    )
    payload = {
        "token": CONFIG['ultramsg_token'],
        "to": to,
        "body": message
    }
    try:
        response = requests.post(url, data=payload)
        logging.info(f"Sent to {to}: {response.status_code}")
    except Exception as e:
        logging.error(f"Send error: {e}")

# ============ ALERT OWNER ============
def alert_owner(customer_phone, rating, complaint, lang):
    rating_text = {
        1: "1/5 - Very Poor ⭐",
        2: "2/5 - Poor ⭐⭐",
        3: "3/5 - Average ⭐⭐⭐"
    }.get(rating, f"{rating}/5")

    message = (
        f"🚨 NEW COMPLAINT\n"
        f"{'=' * 30}\n"
        f"🏪 Restaurant: {CONFIG['restaurant_name']}\n"
        f"📱 Customer: +{customer_phone}\n"
        f"⭐ Rating: {rating_text}\n"
        f"🌐 Language: {'Bengali' if lang == 'bn' else 'English'}\n"
        f"💬 Complaint:\n{complaint}\n"
        f"{'=' * 30}\n"
        f"⏰ Time: {datetime.now().strftime('%d/%m/%Y %I:%M %p')}\n\n"
        f"Reply directly to customer: +{customer_phone}"
    )
    send_whatsapp(CONFIG['owner_number'], message)

# ============ SCHEDULE FOLLOW UP ============
def schedule_followup(phone, lang, name):
    followup_time = (
        datetime.now() +
        timedelta(hours=CONFIG['followup_hours'])
    )

    def send_followup():
        # Only send if user hasn't responded after positive rating
        state = user_data.get(phone, {}).get('state', '')
        if state == 'WAITING_FOLLOWUP':
            msgs = get_messages(lang, name)
            send_whatsapp(phone, msgs['followup'])
            user_data[phone]['state'] = 'FOLLOWUP_SENT'
            logging.info(f"Follow-up sent to {phone}")

    scheduler.add_job(
        send_followup,
        'date',
        run_date=followup_time,
        id=f"followup_{phone}",
        replace_existing=True
    )
    logging.info(
        f"Follow-up scheduled for {phone} "
        f"at {followup_time.strftime('%I:%M %p')}"
    )

# ============ MAIN MESSAGE HANDLER ============
def handle_message(phone, message, customer_name=""):
    message = message.strip()
    message_lower = message.lower()

    # Get or create user session
    if phone not in user_data:
        user_data[phone] = {
            'state': 'START',
            'rating': None,
            'lang': 'en',
            'name': customer_name
        }

    user = user_data[phone]
    state = user['state']

    # Update name if available
    if customer_name:
        user['name'] = customer_name

    # Detect language
    lang = detect_language(message)
    user['lang'] = lang
    msgs = get_messages(lang, user['name'])

    # ============ HANDLE FOLLOWUP RESPONSE ============
    if state == 'FOLLOWUP_SENT':
        if any(word in message_lower for word in
               ['yes', 'done', 'reviewed', 'হ্যাঁ', 'হ্যা', 'করেছি']):
            send_whatsapp(phone, msgs['already_reviewed'])
        else:
            send_whatsapp(phone, msgs['followup'])
        user['state'] = 'START'
        return

    # ============ START / GREETING ============
    greeting_words = [
        'hi', 'hello', 'start', 'hey',
        'হ্যালো', 'হ্যা', 'শুরু', 'সালাম',
        'assalamu', 'আসসালামু'
    ]

    if (state == 'START' or
            any(word in message_lower for word in greeting_words)):
        user['state'] = 'WAITING_RATING'
        send_whatsapp(phone, msgs['welcome'])
        return

    # ============ WAITING FOR RATING ============
    if state == 'WAITING_RATING':
        if message not in ['1', '2', '3', '4', '5']:
            send_whatsapp(phone, msgs['invalid_rating'])
            return

        rating = int(message)
        user['rating'] = rating

        if rating >= 4:
            # POSITIVE EXPERIENCE
            send_whatsapp(phone, msgs['positive'])
            user['state'] = 'WAITING_FOLLOWUP'
            # Schedule follow-up after configured hours
            schedule_followup(phone, lang, user['name'])

        else:
            # NEGATIVE EXPERIENCE
            send_whatsapp(phone, msgs['negative'])
            user['state'] = 'WAITING_COMPLAINT'

        return

    # ============ WAITING FOR COMPLAINT ============
    if state == 'WAITING_COMPLAINT':
        rating = user['rating']
        # Alert owner with full details
        alert_owner(phone, rating, message, lang)
        # Reassure customer
        send_whatsapp(phone, msgs['complaint_received'])
        # Reset state
        user['state'] = 'START'
        return

    # ============ FALLBACK ============
    send_whatsapp(phone, msgs['fallback'])
    user['state'] = 'START'

# ============ WEBHOOK ============
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    if not data:
        return 'ok', 200

    try:
        msg_data = data.get('data', {})
        phone = msg_data.get('from', '').replace('@c.us', '')
        message = msg_data.get('body', '')
        msg_type = msg_data.get('type', '')
        from_me = msg_data.get('fromMe', False)
        customer_name = msg_data.get('notifyName', '')

        # Ignore outgoing messages
        if from_me:
            return 'ok', 200

        # Only handle text messages
        if msg_type != 'chat':
            return 'ok', 200

        # Ignore empty messages
        if not message.strip():
            return 'ok', 200

        logging.info(f"📩 From {phone} ({customer_name}): {message}")
        handle_message(phone, message, customer_name)

    except Exception as e:
        logging.error(f"Webhook error: {e}")

    return 'ok', 200

@app.route('/')
def home():
    active_users = len(user_data)
    return (
        f"✅ {CONFIG['restaurant_name']} WhatsApp Bot\n"
        f"Active sessions: {active_users}\n"
        f"Status: Running"
    )

if __name__ == '__main__':
    keep_alive()
    logging.info(
        f"✅ {CONFIG['restaurant_name']} bot starting..."
    )
    app.run(host='0.0.0.0', port=5000)
