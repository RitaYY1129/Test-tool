from testpilot.parsers.difference_checker import compare_documents
from testpilot.parsers.openapi_parser import OpenApiParser
from testpilot.parsers.curl_parser import parse_curl
from testpilot.parsers.har_parser import HarParser


def test_har_and_difference(tmp_path):
    har = tmp_path / "sample.har"
    har.write_text("""{"log":{"version":"1.2","entries":[{"request":{
      "method":"GET","url":"https://api.example.test/users?id=1",
      "queryString":[{"name":"id","value":"1"}],"headers":[{"name":"Authorization","value":"secret"}]
    },"response":{"status":200,"statusText":"OK"}}]}}""", encoding="utf-8")
    captured = HarParser().parse_file(har)
    curl = parse_curl("curl https://api.example.test/users")
    result = compare_documents(captured, curl)
    assert captured.endpoints[0].security
    assert result["shared_count"] == 1
    assert result["differences"][0]["security_mismatch"]
