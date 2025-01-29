"""Contains all functions for the purpose of logging in and out to Robinhood."""
import getpass
import os
import pickle
import random

from robin_stocks.robinhood.helper import *
from robin_stocks.robinhood.urls import *
from django.apps import apps
from datetime import datetime, timedelta
from django.utils.timezone import now
from django.core.cache import cache
import json


def generate_device_token():
    """This function will generate a token used when loggin on.

    :returns: A string representing the token.

    """
    rands = []
    for i in range(0, 16):
        r = random.random()
        rand = 4294967296.0 * r
        rands.append((int(rand) >> ((3 & i) << 3)) & 255)

    hexa = []
    for i in range(0, 256):
        hexa.append(str(hex(i+256)).lstrip("0x").rstrip("L")[1:])

    id = ""
    for i in range(0, 16):
        id += hexa[rands[i]]

        if (i == 3) or (i == 5) or (i == 7) or (i == 9):
            id += "-"

    return(id)


def respond_to_challenge(challenge_id, sms_code, session):
    """This function will post to the challenge url.

    :param challenge_id: The challenge id.
    :type challenge_id: str
    :param sms_code: The sms code.
    :type sms_code: str
    :returns:  The response from requests.

    """
    url = challenge_url(challenge_id)
    payload = {
        'response': sms_code
    }
    return(request_post(url, session, payload=payload))

def refresh(session, uid, expiresIn=86400, scope='internal'):
    url = login_url()

    UserRobinhoodInfo = apps.get_model("robin_stocks", "UserRobinhoodInfo")
    try:
        brokerageInfo = UserRobinhoodInfo.objects.get(user__id=uid)
    except Exception as e:
        raise Exception(f"This user's brokerage info does not exist: {e}")
    device_token = brokerageInfo.device_token
    refresh_token = brokerageInfo.refresh_token

    payload = {
        'client_id': 'c82SH0WZOsabOXGP2sxqcj34FxkvfnWRZBKlBjFS',
        'grant_type': 'refresh_token',
        'device_token': device_token,
        'refresh_token': refresh_token
    }
    try:
        data = request_post(url, session, payload=payload, jsonify_data=False)
        if data.status_code not in [200, 201, 202, 204]:
            Exception(f"could not make refresh request: {e}")
        data = data.json()
    except Exception as e:
        raise Exception(f"could not make refresh request: {e}")
    
    save_cred(data, payload, uid, session)
    
    return data

def save_cred(data, payload, uid, session):
    if 'access_token' in data:
        token = '{0} {1}'.format(data['token_type'], data['access_token'])
        update_session('Authorization', token, session)
        #set_login_state(uid, True)
        # data['detail'] = "logged in with brand new authentication code."

        UserRobinhoodInfo = apps.get_model("robin_stocks", "UserRobinhoodInfo")
        try:
            brokerageInfo = UserRobinhoodInfo.objects.get(user__id=uid)
        except Exception as e:
            User = apps.get_model("api", "User")
            user = User.objects.get(id=uid)
            brokerageInfo = UserRobinhoodInfo(
                user = user,
                token_type = data['token_type'],
                access_token = data['access_token'],
                refresh_token = data['refresh_token'],
                device_token = payload['device_token'],
                expiration_time = now() + timedelta(seconds=data['expires_in'])
            )
            brokerageInfo.save()
            return
        
        brokerageInfo.token_type = data['token_type']
        brokerageInfo.access_token = data['access_token']
        brokerageInfo.refresh_token = data['refresh_token']
        brokerageInfo.device_token = payload['device_token']
        brokerageInfo.expiration_time = now() + timedelta(seconds=data['expires_in'])
        brokerageInfo.save()
    else:
        if 'detail' in data:
            raise Exception(f"{uid}: {data['detail']}")
        raise Exception(f"{uid}: Received an error response for {data}")

def login(session=None, uid=None, username=None, password=None, expiresIn=86400, 
          scope='internal', by_sms=True, mfa_code=None, challenge_code=None,
          device_token=None):
    """This function will effectively log the user into robinhood by getting an
    authentication token and saving it to the session header. By default, it
    will store the authentication token in a pickle file and load that value
    on subsequent logins.

    :param username: The username for your robinhood account, usually your email.
        Not required if credentials are already cached and valid.
    :type username: Optional[str]
    :param password: The password for your robinhood account. Not required if
        credentials are already cached and valid.
    :type password: Optional[str]
    :param expiresIn: The time until your login session expires. This is in seconds.
    :type expiresIn: Optional[int]
    :param scope: Specifies the scope of the authentication.
    :type scope: Optional[str]
    :param by_sms: Specifies whether to send an email(False) or an sms(True)
    :type by_sms: Optional[boolean]
    :param store_session: Specifies whether to save the log in authorization
        for future log ins.
    :type store_session: Optional[boolean]
    :param mfa_code: MFA token if enabled.
    :type mfa_code: Optional[str]
    :param pickle_path: Allows users to specify the path of the pickle file.
        Accepts both relative and absolute paths.
    :param pickle_name: Allows users to name Pickle token file in order to switch
        between different accounts without having to re-login every time.
    :returns:  A dictionary with log in information. The 'access_token' keyword contains the access token, and the 'detail' keyword \
    contains information on whether the access token was generated or loaded from pickle file.

    """

    device_token = device_token or generate_device_token()
    
    # Challenge type is used if not logging in with two-factor authentication.
    if by_sms:
        challenge_type = "sms"
    else:
        challenge_type = "email"

    payload = {
        'client_id': 'c82SH0WZOsabOXGP2sxqcj34FxkvfnWRZBKlBjFS',
        'expires_in': expiresIn,
        'grant_type': 'password',
        'password': password,
        'scope': scope,
        'username': username,
        'challenge_type': challenge_type,
        'device_token': device_token,
        'try_passkeys': False,
        'token_request_path':'/login',
        'create_read_only_secondary_token':True,
        'request_id': '848bd19e-02bc-45d9-99b5-01bce5a79ea7'
    } 

    if mfa_code:
        payload['mfa_code'] = mfa_code

    url = login_url()
    
    try:
        if challenge_code is not None:
            data = None
        else:
            data = request_post(url, session, payload=payload)
    except Exception as e:
        return f"could not make log in request: {e}"

    # Handle case where mfa or challenge is required.
    if data and 'mfa_required' in data:
        save_mfa_challenge_to_cache(uid, device_token, "That MFA code was not correct. Please type in another MFA code")
        return "mfa incorrect or missing, response cached"
    elif challenge_code is not None or data and 'verification_workflow' in data:
        # import pdb
        # breakpoint()
        validation_output = _validate_sherrif_id(
            session, uid, device_token=device_token, mfa_code=mfa_code, 
            challenge_code=challenge_code, login_attempt_data=data
        )
        if validation_output['error']:
            return validation_output['message']
        if validation_output['device_token']:
            payload['device_token'] = validation_output['device_token']
            data = request_post(url, session, payload=payload)

        # Update Session data with authorization or raise exception with the information present in data.
    if data and 'access_token' in data:
        save_cred(data, payload, uid, session)
        save_login_success_to_cache(uid)
    elif not data:
        raise Exception('Error: Trouble connecting to robinhood API. Check internet connection.')
    return(data)


# make sure to delete these three's cache entries upon response
def save_sms_challenge_to_cache(uid, challenge_type, inquiries_url, challenge_id, 
                                device_token, message):
    cache.delete(f"uid_{uid}_challenge",)
    cache.set(
        f"uid_{uid}_challenge",
        json.dumps({
            "challenge_type": challenge_type,
            "inquiries_url": inquiries_url,
            "challenge_id": challenge_id,
            "device_token": device_token, 
            "message": message}), 
        timeout=120
    )



def save_device_approvals_challenge_to_cache(uid, inquiries_url, challenge_id,
                                             device_token, message):
    cache.delete(f"uid_{uid}_challenge")
    cache.set(
        f"uid_{uid}_challenge",
        json.dumps({
            "challenge_type": "device_approvals",
            "inquiries_url": inquiries_url,
            "challenge_id": challenge_id,
            "device_token": device_token, 
            "message": message
        }), 
        timeout=None
    )

def save_mfa_challenge_to_cache(uid, message):
    cache.delete(f"uid_{uid}_challenge",)
    cache.set(
        f"uid_{uid}_challenge",
        json.dumps({
            "challenge_type": "mfa",
            "inquiries_url": None,
            "challenge_id": None,
            "device_token": None, 
            "message": message
        }),
        timeout=120
    )

def save_login_success_to_cache(uid):
    cache.delete(f"uid_{uid}_challenge",)
    cache.set(
        f"uid_{uid}_challenge",
        json.dumps({
            "challenge_type": None,
            "inquiries_url": None,
            "challenge_id": None,
            "device_token": None, 
            "message": "success"
        }),
        timeout=120
    )

def cache_error(uid):
    cache.delete(f"uid_{uid}_challenge",)
    cache.set(
        f"uid_{uid}_challenge",
        json.dumps({
            "challenge_type": None,
            "inquiries_url": None,
            "challenge_id": None,
            "device_token": None, 
            "message": "error"
        }),
        timeout=120
    )


def _validate_sherrif_id(session, uid, device_token:str, mfa_code:str, 
                         challenge_code:str, login_attempt_data=None):

    # pathfinder to use verification workflow / id to get inquiries id
    # (inquiries id will be used to get info on how to verify self)
    if challenge_code is None:
        url = "https://api.robinhood.com/pathfinder/user_machine/"
        workflow_id = login_attempt_data['verification_workflow']['id']
        payload = {
            'device_id': device_token,
            'flow': 'suv',
            'input':{'workflow_id': workflow_id}
        }
        data = request_post(url, session, payload=payload,json=True)

    # use inquiries id get info on challenge id and challenge type
    if challenge_code is not None or "id" in data:
        # if user gave an challenge (sms) code then we already have this info cached
        if challenge_code is not None:
            challenge_cached_values = cache.get(f"uid_{uid}_challenge")
            if challenge_cached_values is None:
                raise Exception("challenge values not found in cache")
            else:
                challenge_values = json.loads(challenge_cached_values)
                challenge_type = challenge_values["challenge_type"]
                inquiries_url = challenge_values["inquiries_url"]
                challenge_id = challenge_values["challenge_id"]
                device_token = challenge_values["device_token"]
        # use the inquiries id
        else:
            inquiries_url = f"https://api.robinhood.com/pathfinder/inquiries/{data['id']}/user_view/"
            res = request_get(inquiries_url, session)
            challenge_id = res['type_context']["context"]["sheriff_challenge"]["id"]
            challenge_type = res['type_context']["context"]["sheriff_challenge"]["type"]
            # if challenge type is sms, exit now so user can give us the sms code
            if challenge_type == 'sms':
                save_sms_challenge_to_cache(
                    uid, challenge_type, inquiries_url, challenge_id, device_token,
                    "That sms code was not correct. Please type in the new code"
                )
                return {"error": "sms", "message": "sms incorrect or missing, response cached"}
        
        # respond to the challenge 
        if challenge_type == 'app': 
            # confused bc mfa should get handled in login() when 
            # /token request returns 'mfa required'??
            challenge_payload = {'response': mfa_code}
        elif challenge_type == 'sms':
            challenge_payload = {'response': challenge_code or "111111"}
        elif challenge_type == 'prompt':
            # if device approvals, then exit so that
            save_device_approvals_challenge_to_cache(
                uid, 
                f"https://api.robinhood.com/push/{challenge_id}/get_prompts_status/",
                challenge_id,
                device_token,
                "pending"
            )
            return {"error": "device approval needed", "message": "Wait for device approval"}
        
        # import pdb
        # breakpoint()

        challenge_url = f"https://api.robinhood.com/challenge/{challenge_id}/respond/"
        challenge_response = request_post(challenge_url, session, payload=challenge_payload, json=True)
        
        # check if challenge response was successful
        if 'status' in challenge_response and challenge_response["status"] == "validated":
            inquiries_payload = {"sequence":0,"user_input":{"status":"continue"}}
            inquiries_response = request_post(inquiries_url, session, payload=inquiries_payload, json=True)
            if inquiries_response["type_context"]["result"] == "workflow_status_approved":
                return {"error": None, "message": "success", "device_token": device_token if challenge_code else None}
            else:
                raise Exception("workflow status not approved")    
        else:
            if challenge_type == 'app':
                save_mfa_challenge_to_cache(uid, f"That MFA code was not correct. Please type in another MFA code")
                return {"error": "mfa", "message": "mfa incorrect or missing, response cached"}
            elif challenge_type == 'sms':
                save_sms_challenge_to_cache(
                    uid, challenge_type, inquiries_url, challenge_id, device_token,
                    "That sms code was not correct. Please type in the new code"
                )
                return {"error": "sms", "message": "sms incorrect or missing, response cached"}
    raise Exception("Id not returned in user-machine call")



def check_device_approvals(uid):
    import pdb
    breakpoint()
    
    # 
    device_approval_status = cache.get(f"uid_{uid}_challenge")
    if device_approval_status:
        cached_data = json.loads(device_approval_status)
        if cached_data['challenge_type'] != 'device_approvals':
            raise Exception("challenge type is not device approvals")
        
        try:
            response = request_get(cached_data["inquiries_url"], create_session())
        except Exception as e: 
            raise Exception("no response")
        
        if "challenge_status" in response:
            if response["challenge_status"] == "issued":
                return {"message": "device approval issued"}
            elif response["challenge_status"] == "validated":
                cache.delete(f"uid_{uid}_challenge")
                cache.set(
                    f"uid_{uid}_challenge",
                    json.dumps({
                        "challenge_type": "device_approvals",
                        "inquiries_url": cached_data["inquiries_url"],
                        "device_token": cached_data["device_token"], 
                        "message": "device approval validated"
                    }), 
                    timeout=None
                )
                return {"message": "device approval validated"}
            elif response['challenge_status'] in ['failed', 'expired']:
                cache.delete(f"uid_{uid}_challenge")
                raise Exception("device approval failed or expired")

        raise Exception("invalid response")
    else: 
        raise Exception("no cached value")

@login_required
def logout():
    """Removes authorization from the session header.

    :returns: None

    """
    # set_login_state(False)
    update_session('Authorization', None)
