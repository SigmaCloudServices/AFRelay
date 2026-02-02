from fastapi import APIRouter, Depends

from service.api.models.fecae_solicitar import RootModel
from service.api.models.invoice_query import InvoiceBase, InvoiceQueryRequest
from service.api.models.wsfe_caea import (
    WsfeCaeaPeriodoOrdenRequest, WsfeCaeaRegInformativoRequest,
    WsfeCaeaSinMovimientoConsultarRequest, WsfeCaeaSinMovimientoRequest)
from service.api.models.wsfe_params import (WsfeAuthRequest,
                                            WsfeCondicionIvaReceptorRequest)
from service.controllers.consult_invoice_controller import \
    consult_specific_invoice
from service.controllers.request_invoice_controller import \
    request_invoice_controller
from service.controllers.request_last_authorized_controller import \
    get_last_authorized_info
from service.controllers.wsfe_caea_controller import (
    caea_consultar, caea_reg_informativo, caea_sin_movimiento_consultar,
    caea_sin_movimiento_informar, caea_solicitar)
from service.controllers.wsfe_params_controller import (
    get_condicion_iva_receptor, get_max_records_per_request, get_puntos_venta,
    get_types_cbte, get_types_doc, get_types_iva, get_types_monedas,
    get_types_tributos)
from service.utils.jwt_validator import verify_token
from service.utils.logger import logger

router = APIRouter()

@router.post("/wsfe/invoices")
async def generate_invoice(sale_data: RootModel, jwt = Depends(verify_token)) -> dict:
    
    logger.info("Received request to generate invoice at /wsfe/invoices")

    # Preserve AFIP field aliases (e.g. Iva/AlicIva) for SOAP payload keys.
    sale_data = sale_data.model_dump(by_alias=True, exclude_none=True)
    invoice_result = await request_invoice_controller(sale_data)

    return invoice_result


@router.post("/wsfe/invoices/last-authorized")
async def last_authorized(comp_info: InvoiceBase, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch last authorized invoice at /wsfe/invoices/last-authorized")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    last_authorized_info = await get_last_authorized_info(comp_info)

    return last_authorized_info


@router.post("/wsfe/invoices/query")
async def consult_invoice(comp_info: InvoiceQueryRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to query specific invoice at /wsfe/invoices/query")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await consult_specific_invoice(comp_info)

    return result


@router.post("/wsfe/params/max-reg-x-request")
async def max_reg_x_request(comp_info: WsfeAuthRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE max records per request at /wsfe/params/max-reg-x-request")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_max_records_per_request(comp_info)

    return result


@router.post("/wsfe/params/types-cbte")
async def types_cbte(comp_info: WsfeAuthRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE voucher types at /wsfe/params/types-cbte")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_cbte(comp_info)

    return result


@router.post("/wsfe/params/types-doc")
async def types_doc(comp_info: WsfeAuthRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE document types at /wsfe/params/types-doc")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_doc(comp_info)

    return result


@router.post("/wsfe/params/types-iva")
async def types_iva(comp_info: WsfeAuthRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE VAT types at /wsfe/params/types-iva")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_iva(comp_info)

    return result


@router.post("/wsfe/params/types-tributos")
async def types_tributos(comp_info: WsfeAuthRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE tributo types at /wsfe/params/types-tributos")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_tributos(comp_info)

    return result


@router.post("/wsfe/params/types-monedas")
async def types_monedas(comp_info: WsfeAuthRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE currency types at /wsfe/params/types-monedas")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_monedas(comp_info)

    return result


@router.post("/wsfe/params/condicion-iva-receptor")
async def condicion_iva_receptor(comp_info: WsfeCondicionIvaReceptorRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE receptor VAT conditions at /wsfe/params/condicion-iva-receptor")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_condicion_iva_receptor(comp_info)

    return result


@router.post("/wsfe/params/puntos-venta")
async def puntos_venta(comp_info: WsfeAuthRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to fetch WSFE points of sale at /wsfe/params/puntos-venta")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_puntos_venta(comp_info)

    return result


@router.post("/wsfe/caea/solicitar")
async def request_caea(comp_info: WsfeCaeaPeriodoOrdenRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to solicit WSFE CAEA at /wsfe/caea/solicitar")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_solicitar(comp_info)

    return result


@router.post("/wsfe/caea/consultar")
async def consult_caea(comp_info: WsfeCaeaPeriodoOrdenRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to consult WSFE CAEA at /wsfe/caea/consultar")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_consultar(comp_info)

    return result


@router.post("/wsfe/caea/informar")
async def inform_caea(comp_info: WsfeCaeaRegInformativoRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to inform WSFE CAEA at /wsfe/caea/informar")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_reg_informativo(comp_info)

    return result


@router.post("/wsfe/caea/sin-movimiento/consultar")
async def consult_caea_sin_movimiento(comp_info: WsfeCaeaSinMovimientoConsultarRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to consult WSFE CAEA no-movement at /wsfe/caea/sin-movimiento/consultar")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_sin_movimiento_consultar(comp_info)

    return result


@router.post("/wsfe/caea/sin-movimiento/informar")
async def inform_caea_sin_movimiento(comp_info: WsfeCaeaSinMovimientoRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to inform WSFE CAEA no-movement at /wsfe/caea/sin-movimiento/informar")

    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_sin_movimiento_informar(comp_info)

    return result
