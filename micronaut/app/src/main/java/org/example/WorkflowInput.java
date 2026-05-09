package org.example;

import io.micronaut.core.annotation.Introspected;

import java.util.List;
import java.util.Map;

@Introspected
public record WorkflowInput(String name, List<String> aliases, Map<String, Integer> weights) {
}
