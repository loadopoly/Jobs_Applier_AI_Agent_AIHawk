"""
email_oauth2.py
===============
OAuth2 authentication for email services (Gmail, Outlook, etc.)
Supports MFA-protected accounts without needing app-specific passwords.

Providers supported:
- Gmail (Google Workspace)
- Outlook.com / Office 365

Flow:
1. User clicks "Connect with Gmail/Outlook"
2. Browser opens OAuth consent screen
3. User authenticates (with MFA if enabled)
4. App receives access token and refresh token
5. Tokens stored securely in secrets.yaml
6. IMAP connection uses OAuth2 SASL
"""

import base64
import json
import secrets
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

import requests
import yaml

from src.logging import logger


# OAuth2 provider configurations
OAUTH_PROVIDERS = {
    "gmail": {
        "name": "Gmail",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://mail.google.com/",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        # Public client ID for Gmail IMAP (you should replace with your own)
        "client_id": "YOUR_GMAIL_CLIENT_ID",
        "client_secret": "YOUR_GMAIL_CLIENT_SECRET",
    },
    "outlook": {
        "name": "Outlook",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "https://outlook.office365.com/IMAP.AccessAsUser.All offline_access",
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "client_id": "YOUR_OUTLOOK_CLIENT_ID",
        "client_secret": "YOUR_OUTLOOK_CLIENT_SECRET",
    }
}


@dataclass
class OAuth2Tokens:
    """OAuth2 access and refresh tokens."""
    access_token: str
    refresh_token: str
    expires_at: float
    email_address: str
    provider: str
    
    def is_expired(self) -> bool:
        """Check if access token is expired (with 5 min buffer)."""
        return time.time() > (self.expires_at - 300)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "email_address": self.email_address,
            "provider": self.provider,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OAuth2Tokens":
        return cls(
            access_token=d["access_token"],
            refresh_token=d["refresh_token"],
            expires_at=d["expires_at"],
            email_address=d["email_address"],
            provider=d["provider"],
        )


class OAuth2CallbackHandler(BaseHTTPRequestHandler):
    """Handles OAuth2 callback from browser."""
    
    auth_code = None
    error = None
    
    def do_GET(self):
        """Handle callback GET request."""
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if "code" in params:
            OAuth2CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = """
                <html>
                <head><title>Success</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: green;">Authentication Successful!</h1>
                    <p>You can close this window and return to AIHawk.</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode('utf-8'))
        elif "error" in params:
            OAuth2CallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = f"""
                <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: red;">Authentication Failed</h1>
                    <p>Error: {params["error"][0]}</p>
                    <p>Please close this window and try again.</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Suppress access log messages."""
        pass


class EmailOAuth2:
    """OAuth2 authentication manager for email."""
    
    REDIRECT_URI = "http://localhost:8080/oauth2callback"
    
    def __init__(self, provider: str = "gmail"):
        if provider not in OAUTH_PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")
        self.provider = provider
        self.config = OAUTH_PROVIDERS[provider]
    
    def start_auth_flow(self) -> str:
        """
        Start OAuth2 flow and return the authorization URL.
        Opens browser automatically.
        """
        state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.REDIRECT_URI,
            "response_type": "code",
            "scope": self.config["scope"],
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent screen to get refresh token
        }
        
        auth_url = f"{self.config['auth_url']}?{urllib.parse.urlencode(params)}"
        
        logger.info(f"Opening browser for {self.config['name']} authentication...")
        webbrowser.open(auth_url)
        
        return auth_url
    
    def wait_for_callback(self, timeout: int = 300) -> Optional[str]:
        """
        Start local server and wait for OAuth2 callback.
        Returns authorization code or None on timeout/error.
        """
        server = HTTPServer(("localhost", 8080), OAuth2CallbackHandler)
        server.timeout = timeout
        
        logger.info("Waiting for authentication callback...")
        
        # Reset class variables
        OAuth2CallbackHandler.auth_code = None
        OAuth2CallbackHandler.error = None
        
        # Handle one request (the callback)
        server.handle_request()
        server.server_close()
        
        if OAuth2CallbackHandler.error:
            logger.error(f"OAuth2 error: {OAuth2CallbackHandler.error}")
            return None
        
        return OAuth2CallbackHandler.auth_code
    
    def exchange_code_for_tokens(self, auth_code: str, email_address: str) -> OAuth2Tokens:
        """Exchange authorization code for access and refresh tokens."""
        data = {
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "code": auth_code,
            "redirect_uri": self.REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        
        response = requests.post(self.config["token_url"], data=data)
        response.raise_for_status()
        token_data = response.json()
        
        return OAuth2Tokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", ""),
            expires_at=time.time() + token_data.get("expires_in", 3600),
            email_address=email_address,
            provider=self.provider,
        )
    
    def refresh_access_token(self, tokens: OAuth2Tokens) -> OAuth2Tokens:
        """Refresh access token using refresh token."""
        if not tokens.refresh_token:
            raise ValueError("No refresh token available")
        
        data = {
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": tokens.refresh_token,
            "grant_type": "refresh_token",
        }
        
        response = requests.post(self.config["token_url"], data=data)
        response.raise_for_status()
        token_data = response.json()
        
        # Update tokens
        tokens.access_token = token_data["access_token"]
        tokens.expires_at = time.time() + token_data.get("expires_in", 3600)
        # Keep existing refresh token if not provided
        if "refresh_token" in token_data:
            tokens.refresh_token = token_data["refresh_token"]
        
        return tokens
    
    def generate_oauth2_string(self, email: str, access_token: str) -> str:
        """Generate OAuth2 authentication string for IMAP."""
        auth_string = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
        return base64.b64encode(auth_string.encode()).decode()
    
    def authenticate(self, email_address: str) -> OAuth2Tokens:
        """
        Complete OAuth2 flow: open browser, wait for callback, exchange tokens.
        Returns OAuth2Tokens on success.
        """
        # Start auth flow
        self.start_auth_flow()
        
        # Wait for callback
        auth_code = self.wait_for_callback()
        if not auth_code:
            raise Exception("Failed to get authorization code")
        
        # Exchange for tokens
        tokens = self.exchange_code_for_tokens(auth_code, email_address)
        
        logger.info(f"Successfully authenticated {email_address}")
        return tokens


def save_oauth2_tokens(tokens: OAuth2Tokens, secrets_path: Path = Path("data_folder/secrets.yaml")):
    """Save OAuth2 tokens to secrets file."""
    try:
        with open(secrets_path, "r", encoding="utf-8") as fh:
            secrets = yaml.safe_load(fh) or {}
    except Exception:
        secrets = {}
    
    secrets["email_oauth2_tokens"] = tokens.to_dict()
    secrets["email_address"] = tokens.email_address
    secrets["email_provider"] = tokens.provider
    
    with open(secrets_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(secrets, fh, sort_keys=False)


def load_oauth2_tokens(secrets_path: Path = Path("data_folder/secrets.yaml")) -> Optional[OAuth2Tokens]:
    """Load OAuth2 tokens from secrets file."""
    try:
        with open(secrets_path, "r", encoding="utf-8") as fh:
            secrets = yaml.safe_load(fh) or {}
        
        token_data = secrets.get("email_oauth2_tokens")
        if token_data:
            return OAuth2Tokens.from_dict(token_data)
    except Exception as exc:
        logger.warning(f"Failed to load OAuth2 tokens: {exc}")
    
    return None
