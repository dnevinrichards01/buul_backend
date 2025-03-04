from plaid import ApiClient, Configuration
from plaid.api import plaid_api
from accumate_backend.settings import PLAID_CLIENT_ID, PLAID_SECRET, PLAID_HOST

def get_plaid_client():
    """
    Creates and returns a singleton Plaid API client.
    """
    # Configuration for the Plaid API
    configuration = Configuration(
        host=PLAID_HOST,  # Change to production or development as needed
        api_key={
            "clientId": PLAID_CLIENT_ID,
            "secret": PLAID_SECRET
        },
    )
    # Initialize the API client
    api_client = ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)

# Singleton instance
plaid_client = get_plaid_client()
