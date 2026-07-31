from testpilot.parsers.spring_parser import SpringBootParser


def test_spring_controller(tmp_path):
    (tmp_path / "UserRequest.java").write_text(
        """
        public class UserRequest {
          @NotBlank @Size(min=2, max=20)
          private String name;
          @Min(1) @Max(120)
          private Integer age;
        }
        """, encoding="utf-8"
    )
    source = tmp_path / "UserController.java"
    source.write_text(
        """
        @RestController
        @RequestMapping("/api/users")
        public class UserController {
          @GetMapping("/{id}")
          @PreAuthorize("hasRole('USER')")
          public User get(@PathVariable Long id, @RequestHeader(name="X-App", required=false) String app) { }
          @PostMapping("")
          public User create(@Valid @RequestBody UserRequest request) {
            throw new IllegalArgumentException();
          }
        }
        """, encoding="utf-8"
    )
    document = SpringBootParser().parse_directory(tmp_path)
    assert len(document.endpoints) == 2
    assert document.endpoints[0].key == "GET /api/users/{id}"
    assert document.endpoints[0].parameters[0].location == "path"
    assert document.endpoints[0].security
    created = document.endpoints[1]
    schema = created.request_body["content"]["application/json"]["schema"]
    assert "name" in schema["required"]
    assert schema["properties"]["age"]["maximum"] == 120
    assert "400" in created.responses
