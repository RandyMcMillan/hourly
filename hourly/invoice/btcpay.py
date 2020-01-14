"""BTCPay interface

This module handles:

* configuration of hourly to pair with a BTCPay server,
* Generates a BTCPay client using configuration credential
* Processing of BTCPay invoices
"""
from hourly.hourly import get_labor_description, get_hours_worked
from omegaconf import OmegaConf
import sys
from os import path
import hydra


btcpay_not_installed ="""
You must install btcpay-python first:
    pip install btcpay-python
    See BTCPay Server for more info:
        https://btcpayserver.org/
    See btcpay python api for configuration:
        https://bitpay.com/api/#rest-api-resources-invoices-create-an-invoice
"""

btcpay_instructions = """
Initializing hourly-btcpay configuration:

Log in to {} and create a new token:
    Stores > Store settings > Access tokens > Create new token

Fill in the form:
    Label: <any string that will help you remember what this pairing is used for>
    Public key: leave blank

Click save and then copy the 7 digit pairing_code from the success page
"""

# btcpay:
#   host: ${env:BTCPAYSERVER_HOST}
#   tokens:
#     merchant: ${env:BTCPAYSERVER_MERCHANT}
#   pem: btcpayserver.pem # file holding btcpayserver private key
#   return_status: false
#   invoice:
#     currency: null # will be honored if set
#     price: null # will be honored if set, else determined by wage
#     orderId: null 
#     fullNotifications: True
#     extendedNotifications: True
#     transactionSpeed: medium
#     notificationURL: null # https://mywebhook.com
#     notificationEmail: null # myemail@email.com
#     redirectURL: null # https://yourredirecturl.com
#     buyer: 
#       email: null # fox.mulder@trustno.one
#       name: null # Fox Mulder
#       phone: null # 555-123-456
#       address1: null # 2630 Hegal Place
#       address2: null # Apt 42
#       locality: null # Alexandria
#       region: # VA
#       postalCode: # 23242
#       country: # US
#       notify: True
#     itemDesc: null # will be honored if set, else hourly will provide


def get_btcpay_invoice(cfg, labor, current_user, compensation):
    """generates invoice from btcpay config"""
    print("Generating btcpay invoice for {}".format(current_user))
    if compensation is None:
        raise IOError("No compensation provided.")

    # make sure btcpayserver configuration takes precedence

    client = get_btcpay_client(cfg)

    hours_worked = get_hours_worked(labor)

    if cfg.invoice.btcpay.invoice.price is None:
        if compensation.wage is not None:
            # can be fractions of btc
            earnings = float(hours_worked * compensation.wage) 
        else:
            raise IOError("Must specify compensation wage or invoice.price")
        cfg.invoice.btcpay.invoice.price = earnings

    if cfg.invoice.btcpay.invoice.itemDesc is None:
        cfg.invoice.btcpay.invoice.itemDesc = get_labor_description(labor)

    if cfg.invoice.btcpay.invoice.currency is None:
        if compensation.currency is not None:
            cfg.invoice.btcpay.invoice.currency = compensation.currency
        else:
            raise IOError("Must specify invoice.currency (e.g. USD, BTC) or compensation currency")

    print(cfg.invoice.btcpay.invoice.pretty())
    user_confirms = input("Is this correct? (yes/n): ")
    if user_confirms.lower() != 'yes':
        print("Ok, try again later")
        sys.exit()

    btcpay_d = OmegaConf.to_container(cfg.invoice.btcpay.invoice)
    invoice = client.create_invoice(OmegaConf.to_container(cfg.invoice.btcpay.invoice))

    result = OmegaConf.create(invoice)

    if cfg.invoice.btcpay.return_status:
        print(result.pretty())

    return result

def get_btcpay_client(cfg):
    """Reconstruct client credentials"""

    try: 
        from btcpay import BTCPayClient
    except ImportError:
        print('btcpay_not_installed')
        sys.exit()


    # extract host, private key and merchant token
    host = cfg.invoice.btcpay.host
    pem = cfg.invoice.btcpay.pem
    tokens = dict(merchant = cfg.invoice.btcpay.tokens.merchant)

    # see if private key points to a pem file
    pem_filename = hydra.utils.to_absolute_path(cfg.invoice.btcpay.pem)
    if path.exists(pem_filename):
        with open(pem_filename) as pem_file:
            pem = pem_file.read()

    client = BTCPayClient(host = host, pem = pem, tokens = tokens)
    return client


def initialize_btcpay(cfg):
    try: 
        from btcpay import BTCPayClient
    except ImportError:
        print('btcpay_not_installed')
        sys.exit()
        
    btcpay = cfg.invoice.btcpay

    host = input("Enter your btcpay server's host name (blank to quit) :")

    cfg.invoice.btcpay.host = host

    if len(cfg.invoice.btcpay.host) == 0:
        sys.exit()

    print(btcpay_instructions.format(btcpay.host))

    generate_privkey = input("Should hourly generate your private key? (yes/n) ")
    if generate_privkey.lower() == 'yes':
        try:
            from btcpay import crypto
        except ImportError():
            print(btcpay_not_installed)
            sys.exit()

        btcpay.pem = crypto.generate_privkey()

        save_privkey = input("Should hourly save your private key? (yes/n) ")

        if save_privkey == 'yes':
            pem_file = input("Enter private key filename (leave blank for btcpayserver.pem):")
            if len(pem_file) == 0:
                pem_file = 'btcpayserver.pem'
            
            if path.exists(pem_file):
                print("File already exists! Exiting.")
                sys.exit()

            with open(pem_file, 'w') as pem:
                pem.write(btcpay.pem)
                print("private key written to {}".format(btcpay.pem))
                print("Do not commit {} to your repo! List it in .gitignore just to be safe".format(btcpay.pem))
    else:
        print("Ok, assuming your btcpay.pem has not yet been paired already")

    

    client = BTCPayClient(host = btcpay.host, pem = btcpay.pem)

    pairing_code = input("Paste your 7 digit pairing code here: ")
    if len(pairing_code) != 7:
        print("Pairing code is not 7 digits!")
        sys.exit()

    btcpay.tokens = client.pair_client(pairing_code)
    print("merchant token generated")

    save_configuration = input("save configuration? (yes/n) ")
    if save_configuration.lower() == 'yes':
        btcpay_filename = input("enter configuration file name (leave blank for btcpay.yaml):")
        with open(btcpay_filename, 'w') as btcpay_file:
            btcpay_file.write(btcpay.pretty())
            print("btcpay config written to {}".format(btcpay_filename))
            print("Do not commit {} to your repo! List ig in .gitignore just to be safe".format(btcpay_filename))
    
    print("Your btcpay configuration is given below:\n")
    print(btcpay.pretty())

