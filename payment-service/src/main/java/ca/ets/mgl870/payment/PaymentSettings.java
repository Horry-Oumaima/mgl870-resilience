package ca.ets.mgl870.payment;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentSettings {
    private volatile double errorRate;
    private volatile long baseDelayMs;

    public PaymentSettings(@Value("${payment.error-rate}") double errorRate,
                           @Value("${payment.base-delay-ms}") long baseDelayMs) {
        this.errorRate = errorRate;
        this.baseDelayMs = baseDelayMs;
    }

    public double getErrorRate() { return errorRate; }
    public void setErrorRate(double errorRate) { this.errorRate = errorRate; }
    public long getBaseDelayMs() { return baseDelayMs; }
    public void setBaseDelayMs(long baseDelayMs) { this.baseDelayMs = baseDelayMs; }
}