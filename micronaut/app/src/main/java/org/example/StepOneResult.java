package org.example;

import io.micronaut.core.annotation.Introspected;

import java.util.Map;

@Introspected
public record StepOneResult(String greeting, int nameLength, Map<String, Integer> metrics) {
}
