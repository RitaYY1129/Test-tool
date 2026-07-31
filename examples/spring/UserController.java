import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@RestController
@RequestMapping("/api/users")
public class UserController {
    @GetMapping("/{id}")
    @PreAuthorize("hasRole('USER')")
    public String getUser(@PathVariable Long id) {
        return "{}";
    }
}

