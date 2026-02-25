import imaplib
import sys

email = "adam.r.gard09@gmail.com"
pw = sys.argv[1]

try:
    print(f"Attempting to connect to imap.gmail.com:993 for {email}...")
    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    print("SSL Connection established. Attempting login...")
    conn.login(email, pw)
    print("Login successful!")
    conn.logout()
except Exception as e:
    print(f"FAILED: {e}")
