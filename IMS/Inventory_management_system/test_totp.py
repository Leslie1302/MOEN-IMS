import pyotp
from django_otp.util import random_hex

# Create a sample hex key (similar to what random_hex(20) does)
hex_key = random_hex(20)
print(f"Hex Key: {hex_key}")

# PyOTP requires base32 encoding. django-otp handles this internally, 
# but let's see how PyOTP behaves with the raw key in a standalone test.
import base64
# Convert hex to bytes, then base32 encode it
b32_key = base64.b32encode(bytes.fromhex(hex_key)).decode('utf-8')
print(f"Base32 Key: {b32_key}")

totp = pyotp.TOTP(b32_key)
current_code = totp.now()
print(f"Current Code: {current_code}")

print(f"Verify Code (True expected): {totp.verify(current_code)}")

