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


# helper methods

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


# log in and refresh

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
            raise Exception("could not refresh token")
        data = data.json()
    except Exception as e:
        brokerageInfo.previousRefreshSuccess = False
        brokerageInfo.save()
        return
    
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
            brokerageInfo.token_type = data['token_type']
            brokerageInfo.access_token = data['access_token']
            brokerageInfo.refresh_token = data['refresh_token']
            brokerageInfo.device_token = payload['device_token']
            brokerageInfo.expiration_time = now() + timedelta(seconds=data['expires_in'])
            brokerageInfo.previousRefreshSuccess = True
            brokerageInfo.save()
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
    else:
        if 'detail' in data:
            raise Exception(f"{uid}: {data['detail']}")
        raise Exception(f"{uid}: Received an error response for {data}")

def login(session=None, uid=None, username=None, password=None, expiresIn=86400, 
          scope='internal', by_sms=True, mfa_code=None, challenge_code=None,
          device_approval=False, default_to_sms=False):
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

    # load or generate device token
    if challenge_code is not None or mfa_code is not None or device_approval:
        challenge_cached_values = cache.get(f"uid_{uid}_rh_challenge")
        if challenge_cached_values is None:
            save_error_to_cache(
                uid,
                "An internal error occurred. Please log in again."
            )
            return {
                "error": "no cache", 
                "message": "(No cached mfa info) An internal error occured. Please log in again."
            }
        cache_error = True
        challenge_values = json.loads(challenge_cached_values)
        for key in challenge_values:
            if key != "error" and challenge_values[key]:
                cache_error = False
                break
        if cache_error:
            return {
                "error": "no cache", 
                "message": "(No cached mfa info, only error) No cached values associated with this uid. Log in again."
            }
        device_token = challenge_values["device_token"]
    else:
        challenge_cached_values = cache.delete(f"uid_{uid}_rh_challenge")
        device_token = generate_device_token()
    
    # create payload for login endpoint
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

    # make login request unless we are submitting an sms challenge code 
    if challenge_code is not None or mfa_code is not None or device_approval:
        data = None
    else:
        data = request_post(login_url(), session, payload=payload)
            
    # if request_post errors or has non-success status, returs None
    if data is None and (challenge_code is None and mfa_code is None and not device_approval):
        save_error_to_cache(uid, "An internal error occurred. Please log in again.")
        return f"(initial login request returned None) An internal error occurred. Please log in again."
    if data and 'detail' in data and data['detail'] == "Unable to log in with provided credentials.":
        save_error_to_cache(uid, "Incorrect credentials")
        return f"(data retured detail: incorrect credentails) Incorrect credentials"
    # if need mfa app code, retry once user enters it
    if data and 'mfa_required' in data: 
        save_mfa_challenge_to_cache(uid, None, None, device_token,
            "Please enter an MFA code from your OTP authenticator app linked with " + \
                "Robinhood"
        )
        return "(Outside of verification workflow) Please enter an MFA code from your OTP authenticator app linked with " + \
                "Robinhood"
    
    # if need submit challenge code or do mfa before logging in
    elif data and 'verification_workflow' in data:
        validation_output = initial_verification_flow(
            session, uid, device_token=device_token, mfa_code=mfa_code,
            workflow_id=data['verification_workflow']['id']
        )
        if validation_output['error']:
            return f"error: {validation_output['message']}"
        if validation_output['success']:
            data = request_post(login_url(), session, payload=payload)
    elif challenge_code is not None or device_approval:
        validation_output = response_verification_flow(
            session, uid, device_token=device_token, mfa_code=mfa_code, 
            challenge_code=challenge_code, default_to_sms=default_to_sms
        )
        if validation_output['error']:
            return f"error: {validation_output['message']}"
        if validation_output['success']:
            data = request_post(login_url(), session, payload=payload)
    
    # if logged in successfully, save credentials
    if data and 'access_token' in data:
        save_cred(data, payload, uid, session)
        save_login_success_to_cache(uid)
        return "success: logged in, creds saved"
    # edge case error if login endpoint returned nothing
    elif not data:
        save_error_to_cache(uid, "An internal error occurred. Please log in again.")
        return "(second login request returned None) An internal error occurred. Please log in again."
    
    save_error_to_cache(uid, "An internal error occurred. Please log in again.")
    return "(unhandled case) An internal error occurred. Please log in again."

def initial_verification_flow(session, uid, device_token:str, mfa_code:str, 
                              workflow_id:str):

    # takes verification workflow id, returns user machine id
    url = "https://api.robinhood.com/pathfinder/user_machine/"
    payload = {
        'device_id': device_token,
        'flow': 'suv',
        'input':{'workflow_id': workflow_id}
    }
    user_machine_response = request_post(url, session, payload=payload,json=True)
    # check if response valid
    if "id" not in user_machine_response:
        save_error_to_cache(
            uid, 
            "An internal error occurred. Please log in again."
        )
        return {
            "error": "error", 
            "success": None,
            "message": f"(no id in user_machine) An internal error occurred. Please log in again."
        }
    
    # takes user machine id, returns challenge id and challenge type
    inquiries_url = f"https://api.robinhood.com/pathfinder/inquiries/{user_machine_response['id']}/user_view/"
    inquiries_response = request_get(inquiries_url, session)
    try:
        challenge_id = inquiries_response['type_context']["context"]["sheriff_challenge"]["id"]
        challenge_type = inquiries_response['type_context']["context"]["sheriff_challenge"]["type"]
    except:
        if "state_name" in inquiries_response and "Plaid" in inquiries_response["state_name"]:
            response_format = inquiries_response["state_name"]
            error_message = "An internal error occurred. If your account is new, " + \
                "you may need to finish connecting to your bank and uploading " + \
                "documents on the Robinhood website - not the app. \n\nIf you already have, try waiting a few days or contact Buul."
        else:
            response_format = "Unkown response format"
            error_message = "An internal error occurred. Please log in again or contact Buul."
        save_error_to_cache(uid, error_message)
        return {
            "error": "error", 
            "success": None,
            "message": f"{response_format} from pathfinder/inquiries: {inquiries_response}"
        } 
    # if challenge type is sms, exit now so user can give us the sms code
    if challenge_type == 'sms':
        save_sms_challenge_to_cache(
            uid, challenge_type, inquiries_url, challenge_id, device_token,
            "Please enter the code sent to your phone by Robinhood."
        )
        return {
            "error": "sms", 
            "success": None,
            "message": "Please enter the code sent to your phone by Robinhood."
        }
    # if challenge type is device approvals, exit now so user can give complete prompt
    elif challenge_type == 'prompt':
        save_device_approvals_challenge_to_cache(
            uid, inquiries_url, challenge_id, device_token, "Please respond to the prompt in the Robinhood app then return here to click Continue."
        )
        return {
            "error": "device approval needed", 
            "success": None,
            "message": "Wait for device approval"
        }
    # if challenge_type is mfa app code, prepare challenge payload
    elif challenge_type == 'app':
        save_mfa_challenge_to_cache(uid, inquiries_url, challenge_id, device_token,
            "Please enter an MFA code from your OTP authenticator app linked with Robinhood"
        )
        return "enter mfa app code"
        # challenge_payload = {'response': mfa_code}
    # handle unkown challenge type
    else:
        save_error_to_cache(
            uid, 
            "An internal error occurred. Please log in again or contact Buul."
        )
        return {
            "error": "error", 
            "success": None,
            "message": f"Unkown response format from pathfinder/inquiries: {inquiries_response}"
        }

def response_verification_flow(session, uid, device_token, mfa_code, 
                               challenge_code, default_to_sms):

    # retrieve challenge id and challenge type
    challenge_cached_values = cache.get(f"uid_{uid}_rh_challenge")
    if challenge_cached_values is None:
        save_error_to_cache(
            uid,
            "An internal error occurred. Please log in again."
        )
        return {
            "error": "no sms cache", 
            "success": None,
            "message": "No cached values associated with a challenge code. Log in again."
        }
    challenge_values = json.loads(challenge_cached_values)
    challenge_type = challenge_values["challenge_type"]
    inquiries_url = challenge_values["inquiries_url"]
    challenge_id = challenge_values["challenge_id"]
    device_token = challenge_values["device_token"]
    # for if we implement device approvals resend notification
    sequence_num = challenge_values.get("sequence_num", 0) 
    
    # respond to the challenge 
    challenge_validated = False
    prompt_validated = False
    if challenge_type == 'app':
        challenge_payload = {'response': mfa_code}
    elif challenge_type == 'sms':
        challenge_payload = {'response': challenge_code}
    if challenge_type != 'prompt':
        challenge_url = f"https://api.robinhood.com/challenge/{challenge_id}/respond/"
        challenge_response = request_post(challenge_url, session, payload=challenge_payload, json=True)
        challenge_validated = 'status' in challenge_response and challenge_response["status"] == "validated"
    else:
        if default_to_sms:
            inquiries_payload = {
                "sequence":sequence_num,
                "user_input":{"status":"fallback"}
            }
            inquiries_response = request_post(inquiries_url, session, payload=inquiries_payload, json=True)
            challenge_id = inquiries_response['type_context']["context"]["sheriff_challenge"]["id"]
            challenge_type = inquiries_response['type_context']["context"]["sheriff_challenge"]["type"]
            save_sms_challenge_to_cache(
                uid, challenge_type, inquiries_url, challenge_id, device_token,
                "Please enter the code sent to your phone by Robinhood.",
                sequence_num=sequence_num
            )
            return {
                "error": "sms", 
                "success": None,
                "message": "Please enter the code sent to your phone by Robinhood."
            }
        else:    
            prompt_url = f"https://api.robinhood.com/push/{challenge_id}/get_prompts_status/"
            prompt_response = request_get(prompt_url, session)
            prompt_validated = 'challenge_status' in prompt_response and prompt_response["challenge_status"] == "validated"

    # check if challenge response was successful
    if challenge_validated or prompt_validated:
        inquiries_payload = {"sequence":sequence_num,"user_input":{"status":"continue"}}
        inquiries_response = request_post(inquiries_url, session, payload=inquiries_payload, json=True)
        if inquiries_response and "type_context" in inquiries_response and \
            "result" in inquiries_response["type_context"] and \
            inquiries_response["type_context"]["result"] == "workflow_status_approved":
            return {
                "error": None,
                "success": "workflow_status_approved",
                "message": "workflow_status_approved"
            }
        else:
            save_error_to_cache(
                uid,
                "An internal error occurred. Please log in again."
            )
            return {
                "error": "workflow status not approved", 
                "success": None,
                "message": "workflow status not approved despite challenge response status validated"
            }   
    else:
            if challenge_type == 'app':
                save_mfa_challenge_to_cache(
                    uid, inquiries_url, challenge_id, device_token,
                    "That MFA code was not correct or expired. Please enter another one.", 
                    sequence_num=sequence_num
                )
                return {
                    "error": "mfa", 
                    "success": None,
                    "message": "mfa incorrect or missing, response cached"
                }
            elif challenge_type == 'sms':
                save_sms_challenge_to_cache(
                    uid, challenge_type, inquiries_url, challenge_id, device_token, 
                    "That code was not correct. Please type in the new code sent to your phone", 
                    sequence_num=sequence_num
                )
                return {
                    "error": "sms", 
                    "success": None,
                    "message": "sms incorrect or missing, response cached"
                }
            elif challenge_type == 'prompt':
                save_device_approvals_challenge_to_cache(
                    uid, inquiries_url, challenge_id, device_token, 
                    "Please try responding the new prompt in the Robinhood app again and then click continue.", 
                    sequence_num=sequence_num
                )
                return {
                    "error": "prompt", 
                    "success": None,
                    "message": "prompt not yet completed" 
                } 
            else:
                save_error_to_cache(
                    uid,
                    "An internal error occurred. Please log in again."
                )
                return {
                    "error": f"challenge failed with unknown challenge_type: {challenge_type}",
                    "success": None,
                    "message": f"challenge failed with unknown challenge_type: {challenge_type}"
                }   


# save log in information to cache

def save_sms_challenge_to_cache(uid, challenge_type, inquiries_url, challenge_id, 
                                device_token, message, sequence_num=0):
    cache.delete(f"uid_{uid}_rh_challenge",)
    cache.set(
        f"uid_{uid}_rh_challenge",
        json.dumps({
            "challenge_type": challenge_type,
            "inquiries_url": inquiries_url,
            "challenge_id": challenge_id,
            "device_token": device_token, 
            "sequence_num": sequence_num,
            "success": None,
            "error": "enter otp sent to your phone"
        }), 
        timeout=1800
    )

def save_device_approvals_challenge_to_cache(uid, inquiries_url, challenge_id,
                                             device_token, message, sequence_num=0):
    cache.delete(f"uid_{uid}_rh_challenge")
    cache.set(
        f"uid_{uid}_rh_challenge",
        json.dumps({
            "challenge_type": "prompt",
            "inquiries_url": inquiries_url,
            "challenge_id": challenge_id,
            "device_token": device_token, 
            "sequence_num": sequence_num,
            "success": None,
            "error": message
        }), 
        timeout=1800
    )

def save_mfa_challenge_to_cache(uid, inquiries_url, challenge_id, device_token,
                                error_message, sequence_num=0):
    cache.delete(f"uid_{uid}_rh_challenge",)
    cache.set(
        f"uid_{uid}_rh_challenge",
        json.dumps({
            "challenge_type": "app",
            "inquiries_url": inquiries_url,
            "challenge_id": challenge_id,
            "device_token": device_token, 
            "sequence_num": sequence_num,
            "success": None,
            "error": error_message
        }),
        timeout=1800
    )

def save_login_success_to_cache(uid):
    cache.delete(f"uid_{uid}_rh_challenge",)
    cache.set(
        f"uid_{uid}_rh_challenge",
        json.dumps({
            "challenge_type": None,
            "inquiries_url": None,
            "challenge_id": None,
            "device_token": None, 
            "success": "logged in",
            "error": None
        }),
        timeout=1800
    )

def save_error_to_cache(uid, error_message):
    cached_val = cache.get(f"uid_{uid}_rh_challenge",)
    if cached_val:
        val = json.loads(cached_val)
        val["error"] = error_message
        cache.delete(f"uid_{uid}_rh_challenge",)
        cache.set(
            f"uid_{uid}_rh_challenge",
            json.dumps(val),
            timeout=1800
        )
    else:
        cache.delete(f"uid_{uid}_rh_challenge",)
        cache.set(
            f"uid_{uid}_rh_challenge",
            json.dumps({
                "challenge_type": None,
                "inquiries_url": None,
                "challenge_id": None,
                "device_token": None, 
                "success": None,
                "error": error_message
            }),
            timeout=1800
        )