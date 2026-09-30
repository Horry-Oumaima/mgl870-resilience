package ca.ets.mgl870.order;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
public class CatalogController {

    // Ne dépend PAS du Service B : sert à mesurer la propagation des pannes (RQ3)
    @GetMapping("/catalog")
    public List<Map<String, String>> catalog() {
        return List.of(
                Map.of("id", "1", "name", "T-shirt", "price", "25.00"),
                Map.of("id", "2", "name", "Casquette", "price", "18.00"),
                Map.of("id", "3", "name", "Sweat", "price", "45.00"));
    }
}