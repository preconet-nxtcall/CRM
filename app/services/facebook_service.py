import requests
import time
import hmac
import hashlib
from flask import current_app

class FacebookService:
    BASE_URL = "https://graph.facebook.com/v24.0"
    
    @classmethod
    def get_app_secret_proof(cls, access_token):
        """
        Generate appsecret_proof for secure Graph API calls.
        Required if "Require App Secret" is enabled in App Settings.
        """
        app_secret = current_app.config.get('FACEBOOK_APP_SECRET')
        if not app_secret:
            return None
        return hmac.new(
            app_secret.encode('utf-8'),
            msg=access_token.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

    @classmethod
    def get_headers(cls, access_token):
        return {"Authorization": f"Bearer {access_token}"}

    @staticmethod
    def get_user_pages(user_access_token):
        """
        Fetch pages the user has access to (me/accounts).
        Returns pages with their short-lived access tokens.
        """
        url = f"{FacebookService.BASE_URL}/me/accounts"
        params = {
            "fields": "id,name,access_token,tasks",
            "limit": 100,
            "access_token": user_access_token
        }
        
        # Add proof
        proof = FacebookService.get_app_secret_proof(user_access_token)
        if proof:
            params["appsecret_proof"] = proof
            
        resp = requests.get(url, params=params)
        
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch user pages: {resp.text}")
            
        return resp.json().get('data', [])

    @staticmethod
    def exchange_for_long_lived_token(short_lived_token, app_id, app_secret):
        """
        Exchange a short-lived Page Access Token for a long-lived one (60 days).
        """
        url = f"{FacebookService.BASE_URL}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token
        }
        
        resp = requests.get(url, params=params)
        
        if resp.status_code != 200:
            # Fallback or detailed error
            raise Exception(f"Failed to exchange token: {resp.text}")
            
        data = resp.json()
        return data.get('access_token')

    @staticmethod
    def get_oauth_url(app_id, redirect_uri, state=None):
        """
        Generate the Facebook Login URL for Server-Side flow.
        """
        # Scopes required for System User flow (email removed - not needed for Lead Ads)
        scope = "public_profile,business_management,pages_read_engagement,leads_retrieval,pages_show_list,ads_management,pages_manage_metadata"
        
        base = "https://www.facebook.com/v24.0/dialog/oauth"
        url = f"{base}?client_id={app_id}&redirect_uri={redirect_uri}&scope={scope}"
        if state:
            url += f"&state={state}"
        return url

    @staticmethod
    def exchange_code(code, app_id, app_secret, redirect_uri):
        """
        Exchange Authorization Code for User Access Token.
        """
        url = f"{FacebookService.BASE_URL}/oauth/access_token"
        params = {
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code
        }
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            raise Exception(f"OAuth Failed: {resp.text}")
        
        return resp.json().get('access_token')

    @staticmethod
    def get_debug_token(input_token, app_access_token):
        """
        Inspect a token.
        """
        url = f"{FacebookService.BASE_URL}/debug_token"
        params = {
            "input_token": input_token,
            "access_token": app_access_token
        }
        resp = requests.get(url, params=params)
        return resp.json().get("data", {})
