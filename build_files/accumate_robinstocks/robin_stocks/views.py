from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from .serializers import ConnectRobinhoodLoginSerializer
from django.db import transaction
from functools import partial
from .tasks import login_robinhood
from .robinhood import check_device_approvals
from django.core.cache import cache
import json

class ConnectRobinhoodView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Use the serializer to validate input data
        serializer = ConnectRobinhoodLoginSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return HttpResponseBadRequest(e, status=400)
        # Access the validated data
        validated_data = serializer.validated_data
        uid = self.request.user.id
        validated_data['uid'] = uid
        result = transaction.on_commit(
            partial(
                login_robinhood.apply_async,
                kwargs=validated_data
            )
        )
        return HttpResponse("Recieved", status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        # import pdb 
        # breakpoint()
        challenge = cache.get(f"uid_{uid}_challenge")
        try:
            if challenge:
                data_initial = json.loads(challenge)
                if data_initial['challenge_type'] == 'device_approvals':
                    check_device_approvals(uid)
                    challenge_updated = cache.get(f"uid_{uid}_challenge")
                    if challenge_updated:
                        data = json.loads(challenge_updated)
                    else:
                        raise Exception("no updates")
                else:
                    data = data_initial
            else:
                raise Exception("device approval failed or expired")
        except Exception as e:
            data = {"message": str(e) or "no updates"}

        return JsonResponse(data, status=201)
    