package ca.ets.mgl870.order;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryRegistry;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import java.net.SocketTimeoutException;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;

@RestController
public class OrderController {
    private final RestClient paymentClient;
    private final CircuitBreaker circuitBreaker;
    private final Retry retry;
    private final MeterRegistry meterRegistry;
    private final String mode;

    public OrderController(RestClient paymentClient,
                           CircuitBreakerRegistry circuitBreakerRegistry,
                           RetryRegistry retryRegistry,
                           MeterRegistry meterRegistry,
                           @Value("${resilience.config}") String mode) {
        this.mode = mode.toUpperCase();
        if (!Set.of("C0", "C1", "C2", "C3", "C4").contains(this.mode)) {
            throw new IllegalArgumentException("resilience.config invalide : " + mode);
        }
        this.paymentClient = paymentClient;
        this.circuitBreaker = circuitBreakerRegistry.circuitBreaker("payment");
        this.retry = retryRegistry.retry("payment");
        this.meterRegistry = meterRegistry;
    }

    @GetMapping("/order")
    public ResponseEntity<Map<String, String>> order(@RequestParam(defaultValue = "none") String orderId) {
        Supplier<String> call = () -> paymentClient.get()
                .uri("/payment?orderId={id}", orderId)
                .retrieve()
                .body(String.class);

        // Empilement des tactiques selon la configuration (le Retry entoure le Circuit Breaker)
        if (mode.equals("C3") || mode.equals("C4")) {
            call = CircuitBreaker.decorateSupplier(circuitBreaker, call);
        }
        if (mode.equals("C2") || mode.equals("C4")) {
            call = Retry.decorateSupplier(retry, call);
        }

        try {
            call.get();
            count("CONFIRMED");
            return ResponseEntity.ok(Map.of("orderId", orderId, "status", "CONFIRMED"));
        } catch (Exception e) {
            String reason = classify(e);
            count(reason);
            return ResponseEntity.status(503)
                    .body(Map.of("orderId", orderId, "status", "FAILED", "reason", reason));
        }
    }

    @GetMapping("/config")
    public Map<String, String> config() {
        return Map.of("resilienceConfig", mode);
    }

    // Type d'échec, pour la répartition des erreurs
    private String classify(Exception e) {
        if (e instanceof CallNotPermittedException) return "CIRCUIT_OPEN";
        if (e instanceof HttpServerErrorException) return "PAYMENT_ERROR";
        if (e instanceof ResourceAccessException) {
            return (e.getCause() instanceof SocketTimeoutException) ? "TIMEOUT" : "CONNECTION_ERROR";
        }
        return "OTHER";
    }

    private void count(String outcome) {
        Counter.builder("orders.processed")
                .tag("config", mode)
                .tag("outcome", outcome)
                .register(meterRegistry)
                .increment();
    }
}