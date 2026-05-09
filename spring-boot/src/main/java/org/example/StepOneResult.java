package org.example;

import java.util.Map;

record StepOneResult(String greeting, int nameLength, Map<String, Integer> metrics) {
}
