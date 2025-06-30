from buul_backend.retry_db import retry_on_db_error
import robin_stocks.robinhood as r
from ..serializers.rh import RobinhoodAccountListSerializer, RobinhoodAccountSerializer
from rest_framework.exceptions import ValidationError
from django.db.utils import OperationalError

@retry_on_db_error
def rh_load_account_profile(uid):

    import pdb
    breakpoint()

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    result = r.load_account_profile(session)

    try:
        serializer = RobinhoodAccountListSerializer(data=result)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
    except ValidationError as e:
        try:
            serializer = RobinhoodAccountSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return {"error": f"{str(e)}"}
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"{str(e)}"}
