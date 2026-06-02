"""Prompt template engine with variable interpolation.

Supports ``{{variable}}`` syntax with:
- Optional default values: ``{{variable|default}}``
- Required variable validation
- System + user template composition
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptVariable:
    name: str
    description: str | None = None
    default: str | None = None
    required: bool = False


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    system: str | None
    user: str | None
    variables: dict[str, str]


class PromptEngine:
    """Renders prompt templates with variable interpolation."""

    _VAR_PATTERN = re.compile(r"\{\{(\w+)(?:\|([^}]+))?\}\}")

    @classmethod
    def extract_variables(cls, text: str | None) -> list[str]:
        """Extract variable names from a template string."""
        if not text:
            return []
        return [match.group(1) for match in cls._VAR_PATTERN.finditer(text)]

    @classmethod
    def render(
        cls,
        system: str | None,
        user_template: str | None,
        variables: dict[str, str],
    ) -> RenderedPrompt:
        """Render system and user templates with variable substitution.

        Args:
            system: System prompt template (optional)
            user_template: User prompt template (optional)
            variables: Variable values to substitute

        Returns:
            RenderedPrompt with rendered system and user strings
        """
        rendered_system = cls._render_template(system, variables) if system else None
        rendered_user = cls._render_template(user_template, variables) if user_template else None
        return RenderedPrompt(
            system=rendered_system,
            user=rendered_user,
            variables=variables,
        )

    @classmethod
    def validate(
        cls,
        system: str | None,
        user_template: str | None,
        variables: dict[str, str],
    ) -> list[str]:
        """Validate that all required variables are present.

        Returns:
            List of missing required variable names
        """
        all_vars = set()
        if system:
            all_vars.update(cls.extract_variables(system))
        if user_template:
            all_vars.update(cls.extract_variables(user_template))

        missing = []
        for var_name in all_vars:
            if var_name not in variables or variables[var_name] == "":
                # Check if variable has a default in the template
                if system and f"{{{{{var_name}|" in system:
                    continue
                if user_template and f"{{{{{var_name}|" in user_template:
                    continue
                missing.append(var_name)

        return missing

    @classmethod
    def _render_template(cls, template: str, variables: dict[str, str]) -> str:
        """Replace {{var}} and {{var|default}} patterns in template."""
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            if var_name in variables and variables[var_name]:
                return variables[var_name]
            if default is not None:
                return default
            return match.group(0)  # Keep original if no value and no default

        return cls._VAR_PATTERN.sub(_replace, template)
