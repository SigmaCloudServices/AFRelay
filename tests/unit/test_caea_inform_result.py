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


def test_rejected_is_terminal():
    state, msg = classify_inform_response(_resp("R", errors=[{"Code": 10016, "Msg": "fecha"}]))
    assert state == "rejected" and "10016" in msg
