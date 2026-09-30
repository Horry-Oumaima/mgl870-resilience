package ca.ets.mgl870.payment;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/admin/config")
public class AdminController {
    private final PaymentSettings settings;

    public AdminController(PaymentSettings settings) {
        this.settings = settings;
    }

    @GetMapping
    public Map<String, Object> get() {
        return Map.of("errorRate", settings.getErrorRate(),
                      "baseDelayMs", settings.getBaseDelayMs());
    }

    @PostMapping
    public ResponseEntity<?> update(@RequestParam(required = false) Double errorRate,
                                    @RequestParam(required = false) Long baseDelayMs) {
        if (errorRate != null) {
            if (errorRate < 0 || errorRate > 1) {
                return ResponseEntity.badRequest().body(Map.of("error", "errorRate doit être entre 0 et 1"));
            }
            settings.setErrorRate(errorRate);
        }
        if (baseDelayMs != null) {
            if (baseDelayMs < 0) {
                return ResponseEntity.badRequest().body(Map.of("error", "baseDelayMs doit être positif"));
            }
            settings.setBaseDelayMs(baseDelayMs);
        }
        return ResponseEntity.ok(get());
    }
}