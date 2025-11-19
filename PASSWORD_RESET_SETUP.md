# Password Reset Feature - Setup Guide

## ✅ What's Been Implemented

The password reset functionality has been successfully added to the MOEN-IMS application with the following features:

### User Experience Flow
1. **Forgot Password Link**: Added to the sign-in page
2. **Email Request**: User enters their email address
3. **Email Sent**: System sends password reset link via email
4. **Password Reset**: User clicks link and sets new password
5. **Confirmation**: Success message and redirect to sign-in

### Files Created/Modified

#### Templates Created:
- `Inventory/templates/Inventory/password_reset_form.html` - Password reset request form
- `Inventory/templates/Inventory/password_reset_done.html` - Email sent confirmation
- `Inventory/templates/Inventory/password_reset_confirm.html` - New password entry form
- `Inventory/templates/Inventory/password_reset_complete.html` - Success confirmation
- `Inventory/templates/Inventory/emails/password_reset_email.html` - HTML email template
- `Inventory/templates/Inventory/emails/password_reset_email.txt` - Plain text email template
- `Inventory/templates/Inventory/emails/password_reset_subject.txt` - Email subject

#### Files Modified:
- `Inventory/templates/Inventory/signin.html` - Added "Forgot Password?" link
- `Inventory/urls.py` - Added password reset URL routes
- `Inventory_management_system/settings.py` - Added email configuration

---

## 📧 Email Configuration

### Development Mode (Current Setup)
In development mode (DEBUG=True), emails are printed to the console instead of being sent:

```python
# You'll see reset links in your terminal/console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

**To test locally:**
1. Click "Forgot Password?" on sign-in page
2. Enter your email
3. Check your terminal/console for the reset link
4. Copy the link and paste it in your browser

### Production Mode (Heroku)

For production, you need to configure real email sending. Here are the options:

#### Option 1: Gmail (Recommended for Testing)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password**:
   - Go to: https://myaccount.google.com/apppasswords
   - Create a new app password
   - Copy the 16-character password

3. **Set Heroku Config Vars**:
```bash
heroku config:set EMAIL_HOST="smtp.gmail.com"
heroku config:set EMAIL_PORT="587"
heroku config:set EMAIL_USE_TLS="True"
heroku config:set EMAIL_HOST_USER="your-email@gmail.com"
heroku config:set EMAIL_HOST_PASSWORD="your-16-char-app-password"
heroku config:set DEFAULT_FROM_EMAIL="MOEN IMS <your-email@gmail.com>"
```

#### Option 2: SendGrid (Recommended for Production)

SendGrid offers 100 free emails/day:

1. **Sign up at**: https://sendgrid.com/
2. **Create an API Key**
3. **Set Heroku Config Vars**:
```bash
heroku config:set EMAIL_HOST="smtp.sendgrid.net"
heroku config:set EMAIL_PORT="587"
heroku config:set EMAIL_USE_TLS="True"
heroku config:set EMAIL_HOST_USER="apikey"
heroku config:set EMAIL_HOST_PASSWORD="your-sendgrid-api-key"
heroku config:set DEFAULT_FROM_EMAIL="MOEN IMS <noreply@yourdomain.com>"
```

#### Option 3: Mailgun

1. **Sign up at**: https://www.mailgun.com/
2. **Get SMTP credentials**
3. **Set Heroku Config Vars**:
```bash
heroku config:set EMAIL_HOST="smtp.mailgun.org"
heroku config:set EMAIL_PORT="587"
heroku config:set EMAIL_USE_TLS="True"
heroku config:set EMAIL_HOST_USER="your-mailgun-username"
heroku config:set EMAIL_HOST_PASSWORD="your-mailgun-password"
heroku config:set DEFAULT_FROM_EMAIL="MOEN IMS <noreply@yourdomain.com>"
```

---

## 🧪 Testing the Feature

### Local Testing (Development)

1. Start your Django server
2. Go to: http://127.0.0.1:8000/signin/
3. Click "Forgot Password?"
4. Enter your email and submit
5. Check your console/terminal for the reset link
6. Copy and paste the link in your browser
7. Set your new password

### Production Testing (Heroku)

1. Configure email settings (see above)
2. Deploy to Heroku
3. Visit your app's sign-in page
4. Click "Forgot Password?"
5. Enter your email
6. Check your email inbox (and spam folder)
7. Click the link in the email
8. Set your new password

---

## 🔒 Security Features

### Built-in Django Security:
- ✅ **Unique Reset Tokens**: Each reset link is unique and single-use
- ✅ **Time Expiration**: Links expire after 24 hours
- ✅ **User Verification**: Only registered email addresses receive reset links
- ✅ **Secure Hashing**: Tokens are cryptographically secure
- ✅ **HTTPS Support**: Works seamlessly with SSL/TLS

### What Gets Sent:
- Reset link with encrypted user ID and token
- Professional email template with branding
- Clear instructions for the user

---

## 📱 User Instructions

### For End Users:

**Forgot Your Password?**

1. Go to the sign-in page
2. Click the "Forgot Password?" link below the sign-in form
3. Enter the email address you used to register
4. Click "Send Reset Link"
5. Check your email for a message from MOEN IMS
6. Click the "Reset My Password" button in the email
7. Enter your new password twice
8. Click "Reset Password"
9. You'll be redirected to sign in with your new password

**Important Notes:**
- The reset link expires after 24 hours
- You can only use each reset link once
- If you don't receive the email, check your spam folder
- Make sure you're using the email address associated with your account

---

## 🛠 Troubleshooting

### "I didn't receive the reset email"
- Check your spam/junk folder
- Verify you entered the correct email address
- Make sure the email is registered in the system
- In development, check the console/terminal output
- In production, verify email configuration is correct

### "The reset link says it's invalid"
- Links expire after 24 hours - request a new one
- Each link can only be used once
- Make sure you copied the entire URL from the email

### "Email configuration errors on Heroku"
- Verify all config vars are set correctly
- Check that EMAIL_HOST_PASSWORD doesn't have extra spaces
- Ensure DEBUG is set to False in production
- Check Heroku logs: `heroku logs --tail`

### "Authentication error with Gmail"
- Make sure 2-Factor Authentication is enabled
- Use an App Password, not your regular Gmail password
- Generate a new App Password if the old one isn't working

---

## 🚀 Deployment Checklist

Before deploying to production:

- [ ] Set DEBUG=False in production
- [ ] Configure email settings (Heroku config vars)
- [ ] Test email sending in production
- [ ] Verify reset links work end-to-end
- [ ] Check email templates display correctly
- [ ] Test link expiration (wait 24+ hours)
- [ ] Verify SSL/HTTPS is working
- [ ] Test with different email providers (Gmail, Outlook, etc.)

---

## 📊 Email Template Customization

### Branding
The email templates include:
- MOEN-IMS branding and logo
- Ministry of Energy and Green Transition branding
- Professional styling with colors matching your app

### To Customize:
Edit these files:
- `Inventory/templates/Inventory/emails/password_reset_email.html` - HTML version
- `Inventory/templates/Inventory/emails/password_reset_email.txt` - Plain text version
- `Inventory/templates/Inventory/emails/password_reset_subject.txt` - Email subject

---

## 💡 Tips for Production

1. **Use a Dedicated Email Service**: SendGrid, Mailgun, or AWS SES for reliability
2. **Monitor Email Delivery**: Track bounce rates and failures
3. **Set Up SPF/DKIM**: Improves email deliverability
4. **Custom Domain**: Use noreply@yourdomain.com instead of Gmail
5. **Rate Limiting**: Consider adding rate limits to prevent abuse

---

## 📞 Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review Heroku logs: `heroku logs --tail`
3. Test email configuration in Django shell
4. Verify all environment variables are set correctly

---

**Last Updated**: November 12, 2025  
**Feature Version**: 1.0  
**Status**: ✅ Production Ready


