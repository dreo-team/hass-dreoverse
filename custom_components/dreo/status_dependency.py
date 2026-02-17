"""Support for Dreo status dependency."""

from typing import Any

from .coordinator import DreoGenericDeviceData


class DreotStatusDependency:
    """Evaluate select availability based on dependency rules."""

    _status_available_dependencies: list[dict[str, Any]]

    def __init__(self, status_available_dependencies: list[dict[str, Any]]) -> None:
        """Initialize with dependency definitions."""
        self._status_available_dependencies = status_available_dependencies

    def __call__(self, data: DreoGenericDeviceData) -> bool:
        """Allow instances to be called directly for matching check."""
        return self.matches(data)

    def matches(self, data: DreoGenericDeviceData) -> bool:
        """
        Return True if current state matches configured dependency states.

        Each dependency item may include:
        - directive_name: name of the field on data
        - dependency_values: list of allowed values
        - condition: 'and' or 'or' to combine with previous result (default 'and')

        If no valid dependency is defined, default to True (no restriction).
        """
        if not self._status_available_dependencies:
            return True

        combined: bool | None = None

        for dependency in self._status_available_dependencies:
            directive_name = dependency.get("directive_name")
            if not directive_name:
                continue

            condition = str(dependency.get("condition", "and")).lower()
            dependency_values = dependency.get("dependency_values", [])
            current_value = getattr(data, directive_name, None)

            matched = (
                current_value in dependency_values
                if current_value is not None
                else False
            )

            if combined is None:
                combined = matched
                continue

            if condition == "or":
                combined = combined or matched
            else:
                combined = combined and matched

        return True if combined is None else combined
