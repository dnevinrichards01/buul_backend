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

    CHOICES = [
        (DANISH, 'da'),
        (DUTCH, 'nl'),
        (ENGLISH, 'en'),
        (ESTONIAN, 'et'),
        (FRENCH, 'fr'),
        (GERMAN, 'de'),
        (HINDI, 'hi'),
        (ITALIAN, 'it'),
        (LATVIAN, 'lv'),
        (LITHUANIAN, 'lt'),
        (NORWEGIAN, 'no'),
        (POLISH, 'pl'),
        (PORTUGUESE, 'pt'),
        (ROMANIAN, 'ro'),
        (SPANISH, 'es'),
        (SWEDISH, 'sv'),
        (VIETNAMESE, 'vi')
    ] 

class PaymentChannelChoices(Enum):
    ONLINE = 'online'
    INSTORE = 'in store'
    OTHER = 'other'

    CHOICES = [
        (ONLINE, 'online'),
        (INSTORE, 'in store'),
        (OTHER, 'other')
    ]

class TransactionTypeChoices(Enum):
    DIGITAL = 'digital'
    PLACE = 'place'
    SPECIAL = 'special'
    UNRESOLVED = 'unresolved'

    CHOICES = [
        (DIGITAL, 'digital'),
        (PLACE, 'place'),
        (SPECIAL, 'special'),
        (UNRESOLVED, 'unresolved')
    ]

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

    CHOICES = [
        (UNITEDSTATES, 'US'),
        (UNITEDKINGDOM, 'GB'),
        (SPAIN, 'ES'),
        (NETHERLANDS, 'NL'),
        (FRANCE, 'FR'),
        (IRELAND, 'IE'),
        (CANADA, 'CA'),
        (GERMANY, 'DE'),
        (ITALY, 'IT'),
        (POLAND, 'PL'),
        (DENMARK, 'DK'),
        (NORWAY, 'NO'),
        (SWEDEN, 'SE'),
        (ESTONIA, 'EE'),
        (LITHUANIA, 'LT'),
        (LATVIA, 'LV'),
        (PORTUGAL, 'PT'),
        (BELGIUM, 'BE')
    ]