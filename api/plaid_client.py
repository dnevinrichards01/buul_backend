# myapp/plaid_client.py
from plaid import ApiClient, Configuration
from plaid.api import plaid_api

def get_plaid_client():
    """
    Creates and returns a singleton Plaid API client.
    """
    # Configuration for the Plaid API
    configuration = Configuration(
        host="https://sandbox.plaid.com",  # Change to production or development as needed
        api_key={
            "clientId": "671605190a8131001a389fcd",
            "secret": "273215c2e8fa64c8399bbb1e197a45"
        },
    )
    # Initialize the API client
    api_client = ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)

# Singleton instance
plaid_client = get_plaid_client()
