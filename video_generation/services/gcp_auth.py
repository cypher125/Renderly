import os
import threading
from datetime import datetime, timedelta, timezone
from django.conf import settings
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import google.auth

class GCPAuthManager:
    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._lock = threading.Lock()
        self._credentials = None
        self._token = None
        self._expiry = None
        self._scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        self._load_credentials()
        self._initialized = True

    def _load_credentials(self):
        path = settings.GCP_SERVICE_ACCOUNT_FILE or os.getenv('GCP_SERVICE_ACCOUNT_FILE')
        if path and os.path.exists(path):
            self._credentials = Credentials.from_service_account_file(path, scopes=self._scopes)
        else:
            creds, _ = google.auth.default(scopes=self._scopes)
            self._credentials = creds

    def _needs_refresh(self):
        if not self._token or not self._expiry:
            return True
        now_utc = datetime.now(timezone.utc)
        expiry = self._expiry
        if getattr(expiry, 'tzinfo', None) is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return now_utc + timedelta(minutes=2) >= expiry

    def _refresh_locked(self):
        self._credentials.refresh(Request())
        self._token = self._credentials.token
        exp = getattr(self._credentials, 'expiry', None)
        if exp is None:
            exp = datetime.now(timezone.utc) + timedelta(minutes=10)
        elif getattr(exp, 'tzinfo', None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        self._expiry = exp
        return self._token

    def get_access_token(self):
        with self._lock:
            if self._needs_refresh():
                return self._refresh_locked()
            return self._token

    def get_authorization_header(self):
        token = self.get_access_token()
        return {"Authorization": f"Bearer {token}"} if token else {}
