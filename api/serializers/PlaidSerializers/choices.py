from enum import Enum

class LanguageChoices(Enum):
    DANISH = 'da'
    DUTCH = 'nl'
    ENGLISH = 'en'
    ESTONIAN = 'et'
    FRENCH = 'fr'
    GERMAN = 'de'
    HINDI = 'hi'
    ITALIAN = 'it'
    LATVIAN = 'lv'
    LITHUANIAN = 'lt'
    NORWEGIAN = 'no'
    POLISH = 'pl'
    PORTUGUESE = 'pt'
    ROMANIAN = 'ro'
    SPANISH = 'es'
    SWEDISH = 'sv'
    VIETNAMESE = 'vi'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]

class PaymentChannelChoices(Enum):
    ONLINE = 'online'
    INSTORE = 'in store'
    OTHER = 'other'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]

class TransactionTypeChoices(Enum):
    DIGITAL = 'digital'
    PLACE = 'place'
    SPECIAL = 'special'
    UNRESOLVED = 'unresolved'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]

class CountryCodes(Enum):
    UNITEDSTATES = 'US'
    UNITEDKINGDOM = 'GB'
    SPAIN = 'ES'
    NETHERLANDS = 'NL'
    FRANCE = 'FR'
    IRELAND = 'IE'
    CANADA = 'CA'
    GERMANY = 'DE'
    ITALY = 'IT'
    POLAND = 'PL'
    DENMARK = 'DK'
    NORWAY = 'NO'
    SWEDEN = 'SE'
    ESTONIA = 'EE'
    LITHUANIA = 'LT'
    LATVIA = 'LV'
    PORTUGAL = 'PT'
    BELGIUM = 'BE'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]

class LinkTokenProductChoices(Enum):
    ASSETS = 'assets'
    AUTH = 'auth'
    BALANCE_PLUS = 'balance_plus'
    BEACON = 'beacon'
    EMPLOYMENT = 'employment'
    IDENTITY = 'identity'
    INCOME_VERIFICATION = 'income_verification'
    IDENTITY_VERIFICATION = 'identity_verification'
    INVESTMENTS = 'investments'
    LIABILITIES = 'liabilities'
    PAYMENT_INITIATION = 'payment_initiation'
    STANDING_ORDERS = 'standing_orders'
    TRANSACTIONS = 'transactions'
    TRANSFER = 'transfer'
    SIGNAL = 'signal'
    CRA_BASE_REPORT = 'cra_base_report'
    CRA_INCOME_INSIGHTS = 'cra_income_insights'
    CRA_PARTNER_INSIGHTS = 'cra_partner_insights'
    CRA_NETWORK_INSIGHTS = 'cra_network_insights'
    CRA_CASHFLOW_INSIGHTS = 'cra_cashflow_insights'
    LAYER = 'layer'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]

from enum import Enum

class ProductChoices(Enum):
    ASSETS = 'assets'
    AUTH = 'auth'
    BALANCE = 'balance'
    BALANCE_PLUS = 'balance_plus'
    BEACON = 'beacon'
    IDENTITY = 'identity'
    IDENTITY_MATCH = 'identity_match'
    INVESTMENTS = 'investments'
    INVESTMENTS_AUTH = 'investments_auth'
    LIABILITIES = 'liabilities'
    PAYMENT_INITIATION = 'payment_initiation'
    IDENTITY_VERIFICATION = 'identity_verification'
    TRANSACTIONS = 'transactions'
    CREDIT_DETAILS = 'credit_details'
    INCOME = 'income'
    INCOME_VERIFICATION = 'income_verification'
    STANDING_ORDERS = 'standing_orders'
    TRANSFER = 'transfer'
    EMPLOYMENT = 'employment'
    RECURRING_TRANSACTIONS = 'recurring_transactions'
    TRANSACTIONS_REFRESH = 'transactions_refresh'
    SIGNAL = 'signal'
    STATEMENTS = 'statements'
    PROCESSOR_PAYMENTS = 'processor_payments'
    PROCESSOR_IDENTITY = 'processor_identity'
    PROFILE = 'profile'
    CRA_BASE_REPORT = 'cra_base_report'
    CRA_INCOME_INSIGHTS = 'cra_income_insights'
    CRA_PARTNER_INSIGHTS = 'cra_partner_insights'
    CRA_NETWORK_INSIGHTS = 'cra_network_insights'
    CRA_CASHFLOW_INSIGHTS = 'cra_cashflow_insights'
    LAYER = 'layer'
    PAY_BY_BANK = 'pay_by_bank'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]

class ItemUpdateType(Enum):
    BACKGROUND = 'background'
    USER_PRESENT_REQUIRED = 'user_present_required'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]

class ItemAuthMethod(Enum):
    INSTANT_AUTH = 'INSTANT_AUTH'
    INSTANT_MATCH = 'INSTANT_MATCH'
    AUTOMATED_MICRODEPOSITS = 'AUTOMATED_MICRODEPOSITS'
    SAME_DAY_MICRODEPOSITS = 'SAME_DAY_MICRODEPOSITS'
    INSTANT_MICRODEPOSITS = 'INSTANT_MICRODEPOSITS'
    DATABASE_MATCH = 'DATABASE_MATCH'
    DATABASE_INSIGHTS = 'DATABASE_INSIGHTS'
    TRANSFER_MIGRATED = 'TRANSFER_MIGRATED'
    INVESTMENTS_FALLBACK = 'INVESTMENTS_FALLBACK'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.name) for choice in cls]
