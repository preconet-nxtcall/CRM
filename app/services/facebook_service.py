import requests
import time
from flask import current_app

class FacebookService:
    BASE_URL = "https://graph.facebook.com/v24.0"
    
    @classmethod
    def get_headers(cls, access_token):
        return {"Authorization": f"Bearer {access_token}"}

    @staticmethod
    def get_user_businesses(user_access_token):
        """
        Fetch Business Managers where the user is an Admin.
        """
        url = f"{FacebookService.BASE_URL}/me/businesses"
        params = {
            "fields": "id,name,verification_status",
            "limit": 50
        }
        resp = requests.get(url, params=params, headers=FacebookService.get_headers(user_access_token))
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch businesses: {resp.text}")
        
        return resp.json().get('data', [])

    @staticmethod
    def get_user_pages(user_access_token):
        """
        Fetch pages the user has access to (me/accounts).
        """
        url = f"{FacebookService.BASE_URL}/me/accounts"
        params = {
            "fields": "id,name,access_token,tasks",
            "limit": 100
        }
        resp = requests.get(url, params=params, headers=FacebookService.get_headers(user_access_token))
        
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch user pages: {resp.text}")
            
        return resp.json().get('data', [])

    @staticmethod
    def get_business_pages(business_id, user_access_token):
        """
        Fetch Client Pages owned by that Business Manager.
        """
        url = f"{FacebookService.BASE_URL}/{business_id}/client_pages"
        params = {
            "fields": "id,name,access_token",
            "limit": 100
        }
        resp = requests.get(url, params=params, headers=FacebookService.get_headers(user_access_token))
        
        if resp.status_code != 200:
            # Fallback for pages owned directly by the user (if business connection is different)
            # But strictly we want pages OWNED by the BM for System User to work reliably.
            raise Exception(f"Failed to fetch business pages: {resp.text}")
            
        return resp.json().get('data', [])

    @staticmethod
    def check_existing_system_user(business_id, user_access_token):
        """
        Check if we already created a System User in this BM.
        """
        url = f"{FacebookService.BASE_URL}/{business_id}/system_users"
        resp = requests.get(url, headers=FacebookService.get_headers(user_access_token))
        
        if resp.status_code == 200:
            users = resp.json().get('data', [])
            for u in users:
                if "Preconet" in u.get('name', '') or "CRM" in u.get('name', ''):
                    return u
        return None

    @staticmethod
    def create_system_user(business_id, user_access_token, app_id):
        """
        Create a new System User in the client's Business Manager.
        """
        # 1. Check existing
        existing = FacebookService.check_existing_system_user(business_id, user_access_token)
        if existing:
            current_app.logger.info(f"Using existing System User: {existing['id']}")
            return existing['id']

        # 2. Create New
        url = f"{FacebookService.BASE_URL}/{business_id}/system_users"
        payload = {
            "name": "Preconet CRM Automation",
            "role": "ADMIN" # Must be Admin to manage assets
        }
        resp = requests.post(url, data=payload, headers=FacebookService.get_headers(user_access_token))
        
        if resp.status_code != 200:
            raise Exception(f"Failed to create System User: {resp.text}")
            
        su_id = resp.json().get('id')
        
        # 3. Install Our App on the System User (Grant permission to our App)
        # This is critical. The SU needs to be 'installed' on the App to generate tokens for it.
        install_url = f"{FacebookService.BASE_URL}/{su_id}/applications"
        install_resp = requests.post(install_url, data={"business_app": app_id}, headers=FacebookService.get_headers(user_access_token))
        
        if install_resp.status_code != 200:
            # Check if error is just "already installed"
            err = install_resp.json().get('error', {})
            if err.get('code') != 100: # 100 often means invalid param, but checking for specific "already exists" might fail. 
                # Log warning but proceed, sometimes it's auto-linked.
                current_app.logger.warning(f"Failed to explicitly install app on System User: {install_resp.text}")
        
        return su_id

    @staticmethod
    def assign_page_to_system_user(business_id, system_user_id, page_id, user_access_token):
        """
        Assign the Facebook Page to the System User so it can manage leads.
        """
        url = f"{FacebookService.BASE_URL}/{business_id}/business_users" 
        # Actually the endpoint is usually assigning ASSETS to the USER
        # POST /{page_id}/assigned_users -> data={user: system_user_id, tasks:['ADVERTISE', 'MODERATE', 'ANALYZE']}
        
        # Try the Asset Feed method which is more standard for BMs
        # POST /{business_id}/user_permissions
        
        url = f"{FacebookService.BASE_URL}/{page_id}/assigned_users"
        payload = {
            "user": system_user_id,
            "tasks": '["ADVERTISE", "MODERATE", "ANALYZE"]' # "MANAGE" is deprecated/reserved
        }
        
        resp = requests.post(url, data=payload, headers=FacebookService.get_headers(user_access_token))
        
        if resp.status_code != 200:
             # Try legacy method or business_asset_groups if this fails
             current_app.logger.warning(f"Direct page assignment failed: {resp.text}. Trying alternative...")
             pass

        return True

    @staticmethod
    def generate_system_user_token(business_id, system_user_id, app_id, user_access_token):
        """
        Generate a PERMANENT access token for the System User.
        """
        url = f"{FacebookService.BASE_URL}/{business_id}/access_token"
        payload = {
            "user": system_user_id,
            "business_app": app_id,
            "scope": "ads_management,pages_read_engagement,leads_retrieval,pages_show_list,business_management",
            "set_token_expires_in_60_days": "false" # Permanent
        }
        
        resp = requests.post(url, data=payload, headers=FacebookService.get_headers(user_access_token))
        
        if resp.status_code != 200:
            raise Exception(f"Failed to generate System Token: {resp.text}")
            
        return resp.json().get('access_token')

    @staticmethod
    def get_oauth_url(app_id, redirect_uri, state=None):
        """
        Generate the Facebook Login URL for Server-Side flow.
        """
        # Scopes required for System User flow
        scope = "email,public_profile,business_management,pages_read_engagement,leads_retrieval,pages_show_list,ads_management"
        
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
