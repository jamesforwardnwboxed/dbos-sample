package org.example;

import java.util.List;
import java.util.Map;

record WorkflowInput(String name, List<String> aliases, Map<String, Integer> weights) {
}
