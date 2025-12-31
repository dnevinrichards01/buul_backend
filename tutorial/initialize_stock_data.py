from api.models import *
from api.tasks import *

StockData.objects.all().delete()
refresh_stock_data_all()