from __future__ import annotations

from testpilot.parsers.aspnet_parser import AspNetCoreParser
from testpilot.parsers.backend_source_parser import BackendSourceParser


def test_aspnet_controller_dto_and_authorization(tmp_path):
    (tmp_path / "Demo.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>', encoding="utf-8"
    )
    (tmp_path / "CreateUserRequest.cs").write_text(
        """
        public class CreateUserRequest {
            [Required]
            [StringLength(20)]
            public string Name { get; set; } = string.Empty;
            [Range(1, 120)]
            public int Age { get; set; }
        }
        """, encoding="utf-8"
    )
    controller = tmp_path / "UserController.cs"
    controller.write_text(
        """
        [ApiController]
        [Route("api/[controller]")]
        [Authorize]
        public class UserController : ControllerBase {
            [HttpGet("{id}")]
            public IActionResult Get([FromRoute] long id, [FromQuery] bool detail = false) {
                return Ok();
            }

            [HttpPost("create")]
            [AllowAnonymous]
            public IActionResult Create([FromBody] CreateUserRequest request) {
                return BadRequest();
            }
        }
        """, encoding="utf-8"
    )

    document = AspNetCoreParser().parse_directory(tmp_path)
    assert len(document.endpoints) == 2
    assert document.endpoints[0].key == "GET /api/User/{id}"
    assert document.endpoints[0].parameters[0].location == "path"
    assert document.endpoints[0].security
    created = document.endpoints[1]
    assert not created.security
    schema = created.request_body["content"]["application/json"]["schema"]
    assert "Name" in schema["required"]
    assert schema["properties"]["Age"]["maximum"] == 120
    assert "400" in created.responses


def test_backend_source_auto_detects_aspnet(tmp_path):
    (tmp_path / "Demo.csproj").write_text("<Project />", encoding="utf-8")
    (tmp_path / "HealthController.cs").write_text(
        """
        [ApiController]
        [Route("health")]
        public class HealthController : ControllerBase {
            [HttpGet]
            public IActionResult Get() { return Ok(); }
        }
        """, encoding="utf-8"
    )
    parser = BackendSourceParser()
    assert parser.detect(tmp_path) == "aspnet"
    assert parser.parse_directory(tmp_path).endpoints[0].path == "/health"
