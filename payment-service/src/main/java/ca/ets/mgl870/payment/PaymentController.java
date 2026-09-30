package ca.ets.mgl870.payment;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

@RestController
public class PaymentController {
    private final PaymentSettings settings;
    private final Counter accepted;
    private final Counter failed;

    public PaymentController(PaymentSettings settings, MeterRegistry registry) {
        this.settings = settings;
        this.accepted = Counter.builder("payment.requests.received")
                .tag("outcome", "accepted").register(registry);
        this.failed = Counter.builder("payment.requests.received")
                .tag("outcome", "failed").register(registry);
    }

    @GetMapping("/payment")
    public ResponseEntity<Map<String, String>> pay(
            @RequestParam(defaultValue = "none") String orderId) throws InterruptedException {
        // Simule le travail du service (occupe un thread pendant ce temps)
        Thread.sleep(settings.getBaseDelayMs());

        // Échec aléatoire selon le taux d'erreur configuré
        if (ThreadLocalRandom.current().nextDouble() < settings.getErrorRate()) {
            failed.increment();
            return ResponseEntity.status(500).body(Map.of("orderId", orderId, "status", "FAILED"));
        }
        accepted.increment();
        return ResponseEntity.ok(Map.of("orderId", orderId, "status", "ACCEPTED"));
    }
}