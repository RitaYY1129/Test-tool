from testpilot.parsers.apifox_parser import ApifoxParser


def test_native_apifox_query_and_body_fields_are_normalized():
    endpoints = []
    ApifoxParser()._walk({
        "method": "POST", "path": "/alarms/acknowledge?id=", "name": "Acknowledge",
        "requestBody": {
            "type": "json",
            "parameters": [
                {"name": "reason", "type": "string", "description": "acknowledgement reason", "value": "handled"},
            ],
        },
    }, [], endpoints, "native.json")
    endpoint = endpoints[0]
    assert endpoint.path == "/alarms/acknowledge"
    assert endpoint.parameters[0].name == "id"
    media = endpoint.request_body["content"]["application/json"]
    assert media["schema"]["properties"]["reason"]["description"] == "acknowledgement reason"
    assert media["example"] == {"reason": "handled"}
