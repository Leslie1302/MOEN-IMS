#!/usr/bin/env python3
"""
Download Amazon RDS SSL certificate for secure database connections.
"""
import os
import ssl
import urllib.request
from pathlib import Path

# Certificate URL
CERT_URL = "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"
CERT_PATH = Path(__file__).parent / "global-bundle.pem"

def download_certificate():
    """Download the RDS SSL certificate."""
    try:
        print(f"Downloading RDS SSL certificate from {CERT_URL}...")
        
        # Create a custom SSL context that doesn't verify certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Download the certificate
        with urllib.request.urlopen(CERT_URL, context=ssl_context) as response:
            with open(CERT_PATH, 'wb') as f:
                f.write(response.read())
        
        print(f"✓ Certificate downloaded to: {CERT_PATH}")
        print("Certificate is ready to use with your PostgreSQL connection.")
        
    except Exception as e:
        print(f"Error downloading certificate: {e}")
        print("You can manually download the certificate from:")
        print("https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem")
        print("and save it as 'global-bundle.pem' in your project root.")

if __name__ == "__main__":
    download_certificate()
