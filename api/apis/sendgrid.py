from sendgrid import SendGridAPIClient
from buul_backend.settings import SENDGRID_API_KEY

sendgrid_client = SendGridAPIClient(SENDGRID_API_KEY)

