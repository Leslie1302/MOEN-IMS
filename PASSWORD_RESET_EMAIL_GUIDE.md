# Password Reset Email Guide

## 🔍 Why You're Not Receiving Emails

The password reset system works differently in **development** vs **production**.

---

## 📧 Development Mode (Local Testing)

### How It Works:
When running locally with `DEBUG=True`, password reset emails are **printed to your console/terminal** where the Django server is running. They are **NOT sent to your email inbox**.

### How to Find Your Reset Link:

1. **Start your Django server** (if not already running):
   ```bash
   cd IMS\Inventory_management_system
   python manage.py runserver
   ```

2. **Go to the password reset page**: 
   - Visit: http://127.0.0.1:8000/password-reset/
   - Enter your email address
   - Click "Send Reset Link"

3. **Check your console/terminal** where the server is running:
   - Look for output similar to this:
   ```
   Content-Type: text/plain; charset="utf-8"
   MIME-Version: 1.0
   Content-Transfer-Encoding: 7bit
   Subject: Password Reset Request - MOEN IMS
   From: MOEN IMS <noreply@localhost>
   To: youremail@example.com
   Date: Wed, 13 Nov 2025 16:03:00 -0000
   
   Hello username,
   
   You've requested to reset your password for your MOEN-IMS account.
   
   To reset your password, click the link below:
   http://127.0.0.1:8000/password-reset-confirm/MQ/xxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxx/
   
   This link will expire in 24 hours.
   ```

4. **Copy the reset link** from the console and paste it into your browser

5. **Set your new password**

---

## 🌐 Production Mode (Deployed to Heroku/Server)

### How It Works:
When deployed with `DEBUG=False`, password reset emails are **sent via SMTP** to the user's actual email inbox.

### Setup Requirements:

#### Option 1: Gmail (Recommended for Testing)

1. **Enable 2-Factor Authentication** on your Gmail account

2. **Generate an App Password**:
   - Go to: https://myaccount.google.com/apppasswords
   - Create a new app password
   - Copy the 16-character password

3. **Set Environment Variables on Heroku**:
   ```bash
   heroku config:set DJANGO_DEBUG="False"
   heroku config:set EMAIL_HOST="smtp.gmail.com"
   heroku config:set EMAIL_PORT="587"
   heroku config:set EMAIL_USE_TLS="True"
   heroku config:set EMAIL_HOST_USER="your-email@gmail.com"
   heroku config:set EMAIL_HOST_PASSWORD="your-16-char-app-password"
   heroku config:set DEFAULT_FROM_EMAIL="MOEN IMS <your-email@gmail.com>"
   ```

#### Option 2: SendGrid (100 Free Emails/Day)

1. **Sign up at**: https://sendgrid.com/
2. **Create an API Key**
3. **Set Environment Variables**:
   ```bash
   heroku config:set DJANGO_DEBUG="False"
   heroku config:set EMAIL_HOST="smtp.sendgrid.net"
   heroku config:set EMAIL_PORT="587"
   heroku config:set EMAIL_USE_TLS="True"
   heroku config:set EMAIL_HOST_USER="apikey"
   heroku config:set EMAIL_HOST_PASSWORD="your-sendgrid-api-key"
   heroku config:set DEFAULT_FROM_EMAIL="MOEN IMS <noreply@moen-ims.org>"
   ```

### Testing in Production:

1. Visit your deployed app's sign-in page
2. Click "Forgot Password?"
3. Enter your email
4. **Check your email inbox** (and spam folder)
5. Click the link in the email
6. Set your new password

---

## ⚙️ Current Configuration Status

Your system is now configured with:

- ✅ **Fixed DEBUG logic**: Now more intuitive (defaults to `True` for development)
- ✅ **Development email**: Prints to console with proper `FROM` address
- ✅ **Production email**: Uses SMTP when environment variables are set
- ✅ **Middleware fix**: Password reset URLs are now accessible without login

---

## 🔧 Quick Toggle Between Modes

### Switch to Production Mode (send real emails):
```bash
# Set environment variable (Windows)
set DJANGO_DEBUG=False

# Or add to .env file:
DJANGO_DEBUG=False
```

### Switch to Development Mode (console emails):
```bash
# Set environment variable (Windows)
set DJANGO_DEBUG=True

# Or add to .env file:
DJANGO_DEBUG=True
```

### Restart your Django server after changing modes:
```bash
# Stop the server (Ctrl+C)
# Then restart:
python manage.py runserver
```

---

## 🛠️ Troubleshooting

### "I still don't see the email in my console"
- Make sure you're looking at the **terminal/console where Django server is running**
- The email output appears AFTER you submit the password reset form
- Scroll up in your terminal to find the email content

### "The reset link doesn't work"
- Links expire after 24 hours
- Links can only be used once
- Make sure you copied the complete URL from the console

### "Emails not being sent in production"
- Verify all EMAIL_* environment variables are set correctly on Heroku
- Check Heroku logs: `heroku logs --tail`
- Verify your SMTP credentials are correct
- For Gmail: Make sure 2FA is enabled and you're using an App Password (not your regular password)

---

## 📝 Summary

- **Local Development**: Password reset emails appear in your **console/terminal**
- **Production**: Password reset emails are sent to user's **email inbox**
- **Setup**: Production requires SMTP configuration via environment variables
- **Testing**: Always check your terminal output when testing locally

For more details, see: `PASSWORD_RESET_SETUP.md`
