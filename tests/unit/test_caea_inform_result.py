from service.caea_resilience.outbox_worker import classify_inform_response


def _resp(resultado, errors=None, obs=None):
    det = {"Resultado": resultado}
    if obs:
        det["Observaciones"] = {"Obs": obs}
    return {"status": "success", "response": {
        "FeCabResp": {"Resultado": resultado},
        "FeDetResp": {"FECAEADetResponse": [det]},
        "Errors": {"Err": errors} if errors else None}}


def test_accepted():
    assert classify_inform_response(_resp("A"))[0] == "accepted"


def test_accepted_with_observations_keeps_message():
    state, msg = classify_inform_response(_resp("A", obs=[{"Code": 1, "Msg": "obs"}]))
    assert state == "accepted" and "obs" in msg


def test_observed_is_accepted_and_keeps_observation():
    state, msg = classify_inform_response(_resp("O", obs=[{"Code": 7, "Msg": "observado"}]))
    assert state == "accepted" and "observado" in msg


def test_errors_only_response_is_retry_not_rejected():
    response = {"status": "success", "response": {"Errors": {"Err": [{"Code": 600, "Msg": "token"}]}}}
    state, msg = classify_inform_response(response)
    assert state == "retry" and "600" in msg


def test_empty_response_is_retry():
    state, msg = classify_inform_response({"status": "success", "response": None})
    assert state == "retry" and msg == "Respuesta de ARCA sin Resultado"


def test_rejected_without_detail_has_default_message():
    assert classify_inform_response(_resp("R")) == ("rejected", "Resultado R sin detalle")


def test_rejected_is_terminal():
    state, msg = classify_inform_response(_resp("R", errors=[{"Code": 10016, "Msg": "fecha"}]))
    assert state == "rejected" and "10016" in msg
