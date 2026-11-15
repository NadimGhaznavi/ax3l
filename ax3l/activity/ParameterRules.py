"""Present schema constraints as compact English choice rules."""


def parameter_rules(field: dict) -> str:
    rules = ["whole number" if field["type"] == "integer" else "number"]
    if "enum" in field:
        rules.append("one of " + ", ".join(str(value) for value in field["enum"]))
    else:
        if "minimum" in field:
            rules.append(f"at least {field['minimum']}")
        if "exclusiveMinimum" in field:
            rules.append(f"above {field['exclusiveMinimum']}")
        if "maximum" in field:
            rules.append(f"at most {field['maximum']}")
        if "exclusiveMaximum" in field:
            rules.append(f"below {field['exclusiveMaximum']}")
        if "multipleOf" in field:
            rules.append(f"multiple of {field['multipleOf']}")
    return "; ".join(rules) + "."
