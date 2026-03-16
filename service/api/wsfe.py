from fastapi import APIRouter

from service.api.models.fecae_solicitar import RootModel
from service.api.models.invoice_query import InvoiceBase, InvoiceQueryRequest
from service.api.models.wsfe_caea import (
    WsfeCaeaPeriodoOrdenRequest, WsfeCaeaRegInformativoRequest,
    WsfeCaeaSinMovimientoConsultarRequest, WsfeCaeaSinMovimientoRequest)
from service.api.models.wsfe_params import (WsfeAuthRequest,
                                            WsfeCondicionIvaReceptorRequest,
                                            WsfeCotizacionRequest)
from service.controllers.consult_invoice_controller import consult_specific_invoice
from service.controllers.request_invoice_controller import request_invoice_controller
from service.controllers.request_last_authorized_controller import get_last_authorized_info
from service.controllers.wsfe_caea_controller import (
    caea_consultar, caea_reg_informativo, caea_sin_movimiento_consultar,
    caea_sin_movimiento_informar, caea_solicitar)
from service.controllers.wsfe_params_controller import (
    get_actividades, get_condicion_iva_receptor, get_cotizacion,
    get_max_records_per_request, get_puntos_venta, get_types_cbte,
    get_types_concepto, get_types_doc, get_types_iva, get_types_monedas,
    get_types_opcional, get_types_paises, get_types_tributos)
from service.tenants.billing import debit_after_call, make_billing_dependency
from service.utils.logger import logger

router = APIRouter()


@router.post("/wsfe/invoices")
async def generate_invoice(
    sale_data: RootModel,
    billing=make_billing_dependency("wsfe_invoice"),
) -> dict:
    tenant = billing["tenant"]
    logger.info("Received /wsfe/invoices for tenant %s", tenant["id"])
    sale_data = sale_data.model_dump(by_alias=True, exclude_none=True)
    result = await request_invoice_controller(tenant["id"], sale_data)
    debit_after_call(billing, reference=f"wsfe_invoice:{tenant['cuit']}")
    return result


@router.post("/wsfe/invoices/last-authorized")
async def last_authorized(
    comp_info: InvoiceBase,
    billing=make_billing_dependency("wsfe_last_authorized"),
) -> dict:
    tenant = billing["tenant"]
    logger.info("Received /wsfe/invoices/last-authorized for tenant %s", tenant["id"])
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_last_authorized_info(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/invoices/query")
async def consult_invoice(
    comp_info: InvoiceQueryRequest,
    billing=make_billing_dependency("wsfe_query"),
) -> dict:
    tenant = billing["tenant"]
    logger.info("Received /wsfe/invoices/query for tenant %s", tenant["id"])
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await consult_specific_invoice(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/max-reg-x-request")
async def max_reg_x_request(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_max_records_per_request(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-cbte")
async def types_cbte(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_cbte(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-doc")
async def types_doc(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_doc(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-iva")
async def types_iva(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_iva(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-tributos")
async def types_tributos(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_tributos(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-monedas")
async def types_monedas(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_monedas(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/condicion-iva-receptor")
async def condicion_iva_receptor(
    comp_info: WsfeCondicionIvaReceptorRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_condicion_iva_receptor(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/puntos-venta")
async def puntos_venta(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_puntos_venta(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/cotizacion")
async def cotizacion(
    comp_info: WsfeCotizacionRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_cotizacion(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-concepto")
async def types_concepto(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_concepto(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-opcional")
async def types_opcional(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_opcional(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/types-paises")
async def types_paises(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_types_paises(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/params/actividades")
async def actividades(
    comp_info: WsfeAuthRequest,
    billing=make_billing_dependency("wsfe_params"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await get_actividades(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/caea/solicitar")
async def request_caea(
    comp_info: WsfeCaeaPeriodoOrdenRequest,
    billing=make_billing_dependency("wsfe_caea_solicitar"),
) -> dict:
    tenant = billing["tenant"]
    logger.info("Received /wsfe/caea/solicitar for tenant %s", tenant["id"])
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_solicitar(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/caea/consultar")
async def consult_caea(
    comp_info: WsfeCaeaPeriodoOrdenRequest,
    billing=make_billing_dependency("wsfe_caea_consultar"),
) -> dict:
    tenant = billing["tenant"]
    logger.info("Received /wsfe/caea/consultar for tenant %s", tenant["id"])
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_consultar(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/caea/informar")
async def inform_caea(
    comp_info: WsfeCaeaRegInformativoRequest,
    billing=make_billing_dependency("wsfe_caea_informar"),
) -> dict:
    tenant = billing["tenant"]
    logger.info("Received /wsfe/caea/informar for tenant %s", tenant["id"])
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_reg_informativo(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/caea/sin-movimiento/consultar")
async def consult_caea_sin_movimiento(
    comp_info: WsfeCaeaSinMovimientoConsultarRequest,
    billing=make_billing_dependency("wsfe_caea_consultar"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_sin_movimiento_consultar(tenant["id"], comp_info)
    debit_after_call(billing)
    return result


@router.post("/wsfe/caea/sin-movimiento/informar")
async def inform_caea_sin_movimiento(
    comp_info: WsfeCaeaSinMovimientoRequest,
    billing=make_billing_dependency("wsfe_caea_informar"),
) -> dict:
    tenant = billing["tenant"]
    comp_info = comp_info.model_dump(by_alias=True, exclude_none=True)
    result = await caea_sin_movimiento_informar(tenant["id"], comp_info)
    debit_after_call(billing)
    return result
