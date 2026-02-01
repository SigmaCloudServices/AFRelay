import os

from service.utils.logger import logger

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

IS_WSAA_PRODUCTION = os.getenv("WSAA_PRODUCTION", "false").lower() == "true"
IS_WSFE_PRODUCTION = os.getenv("WSFE_PRODUCTION", "false").lower() == "true"
IS_WSPCI_PRODUCTION = os.getenv("WSPCI_PRODUCTION", "false").lower() == "true"

logger.info(f"WSAA environment: {'Production' if IS_WSAA_PRODUCTION else 'Homologation'}")
logger.info(f"WSFE environment: {'Production' if IS_WSFE_PRODUCTION else 'Homologation'}")
logger.info(f"WSPCI environment: {'Production' if IS_WSPCI_PRODUCTION else 'Homologation'}")

def get_wsaa_wsdl() -> str:
    if IS_WSAA_PRODUCTION:
        filename = "wsaa_prod.wsdl"
        return os.path.join(CURRENT_DIR, filename)
    else:
        filename = "wsaa_homo.wsdl"
        return os.path.join(CURRENT_DIR, filename)

def get_wsfe_wsdl() -> str:
    if IS_WSFE_PRODUCTION:
        filename = "wsfe_prod.wsdl"
        return os.path.join(CURRENT_DIR, filename)
    else:
        filename = "wsfe_homo.wsdl"
        return os.path.join(CURRENT_DIR, filename)

def get_wspci_wsdl() -> str:
    if IS_WSPCI_PRODUCTION:
        filename = "wspci_prod.wsdl"
        return os.path.join(CURRENT_DIR, filename)
    else:
        filename = "wspci_homo.wsdl"
        return os.path.join(CURRENT_DIR, filename)
