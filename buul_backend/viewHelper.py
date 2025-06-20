from enum import Enum
from django.http import JsonResponse
from rest_framework.exceptions import ValidationError
from django.db.utils import OperationalError
import json

class LogState(Enum):
    VAL_ERR_MESSAGE = "failed_validation_with_error_message"
    VAL_ERR_NO_MESSAGE = "failed_validation_without_error_message"
    VAL_ERR_INTERNAL = "failed_validation_unknown"
    ERR_NO_MESSAGE = "error_with_error_message"
    ERR_MESSAGE = "error_without_error_message"
    SUCCESS = "success"
    BACKGROUND_TASK_WAITING = "waiting_for_background_task_to_finish"
    BACKGROUND_TASK_MISFORMATTED = "background_task_returned_both_success_error"
    BACKGROUND_TASK_ERR = "background_task_error"
    BACKGROUND_TASK_NO_CACHE = "no_cache_soexpired_or_error"
    INTERNAL_ERR = "internal_error"
    RH_MFA = "rh_req"


def cached_task_logging_info(cached_string):
    cached_value = json.loads(cached_string)
    if cached_value["success"] is None and cached_value["error"] is not None:
        if cached_value["error"] == "We could not find a connection between " + \
            "you and this institution to update. Please create a new " + \
            "connection or contact Buul.":
            status = 200
            log_state = LogState.ERR_MESSAGE
            errors = {"error": cached_value["error"]}
        else:
            status = 400
            log_state = LogState.BACKGROUND_TASK_ERR
            errors = {"error": cached_value["error"]}
    elif cached_value["success"] is None and cached_value["error"] is None:
        status = 200
        log_state = LogState.BACKGROUND_TASK_WAITING
        errors = None
    elif cached_value["success"] is not None and cached_value["error"] is None:
        status = 200
        log_state = LogState.SUCCESS
        errors = None
    else:
        status = 400
        log_state = LogState.BACKGROUND_TASK_MISFORMATTED
        errors = {"error": cached_value["error"]}
    return status, log_state, errors

def log(logger, instance, status, state, errors=None, user=None, 
        pre_account_id=None):
    if instance.authentication_classes:
        user = instance.request.user

    log = logger(
        name = instance.__class__.__name__,
        method = instance.request.method,
        user = user,
        state = state,
        errors = errors,
        status = status,
        pre_account_id = pre_account_id
    )
    log.save()

def validate(logger, serializer, instance, fields_to_correct=[], fields_to_fail=[],
             correct_all = False, fail_all = False, 
             edit_error_message=lambda x: x, rename_field=lambda x: x):
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as e:
        # validation errors which we have no tolerance for
        error_messages = {}
        fields_to_fail_final = e.detail if fail_all else fields_to_fail
        for field in fields_to_fail_final:
            if field in e.detail and len(e.detail[field]) >= 1:
                error_messages[field] = e.detail[field][0]
        if len(error_messages) > 0:
            status = 400
            pre_account_id = dict(instance.request.data).get('pre_account_id', None)
            log(logger, instance, status, LogState.VAL_ERR_NO_MESSAGE, 
                errors = error_messages, pre_account_id = pre_account_id)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                }, 
                status = status
            )
        # validation errors which we send error messages for
        error_messages = {}
        fields_to_correct_final = e.detail if correct_all else fields_to_correct
        for field in fields_to_correct_final:
            if field in e.detail and len(e.detail[field]) >= 1:
                error_message = e.detail[field][0]
                error_messages[rename_field(field)] = edit_error_message(error_message)
            else:
                error_messages[rename_field(field)] = None
        status = 200
        pre_account_id = dict(instance.request.data).get('pre_account_id', None)
        log(logger, instance, status, LogState.VAL_ERR_MESSAGE, 
            errors = error_messages, pre_account_id = pre_account_id)
        return JsonResponse(
            {
                "success": None, 
                "error": error_messages
            }, 
            status=status
        )
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        # unknown error
        status = 400
        pre_account_id = dict(instance.request.data).get('pre_account_id', None)
        log(logger, instance, status, LogState.VAL_ERR_INTERNAL, 
            errors = {"error": str(type(e))}, pre_account_id = pre_account_id)
        return JsonResponse(
            {
                "success": None, 
                "error": str(type(e))
            }, 
            status=status
        )


