"""The tool registry (plan section 7, "Tool registry"): identity always comes from the verified
principal, no tool schema exposes identity, and arguments are validated."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from factories.principals import make_principal
from support.specs import need

from ragassist.shared.security.jwt import UserRole

IDENTITY_FIELDS = {"tenant_id", "user_id", "role"}
OTHER_TENANT = UUID("b0000000-0000-0000-0000-00000000000b")


def walk_property_names(schema: object) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                names |= set(value)
                for child in value.values():
                    names |= walk_property_names(child)
            else:
                names |= walk_property_names(value)
    elif isinstance(schema, list):
        for item in schema:
            names |= walk_property_names(item)
    return names


@pytest.fixture
def echo_tool_factory():  # type: ignore[no-untyped-def]
    spec_cls = need("actions.ToolSpec")
    seen: list[object] = []

    async def handler(principal, arguments):  # type: ignore[no-untyped-def]
        seen.append(principal)
        return {"tenant": str(principal.tenant_id)}

    def build(*, is_write: bool = False, schema: dict | None = None):  # type: ignore[no-untyped-def]
        return spec_cls(
            name="echo",
            description="Echo the caller's tenant.",
            input_schema=schema
            or {
                "type": "object",
                "properties": {"month": {"type": "string"}},
                "required": ["month"],
            },
            is_write=is_write,
            handler=handler,
        )

    return build, seen


class TestSchemasNeverExposeIdentity:
    def test_no_default_tool_takes_a_tenant_user_or_role_argument(self) -> None:
        saas = need("actions.SaaSClient")  # the production client is required to build the tools
        import httpx

        tools = need("actions.default_tools")(saas(http=httpx.AsyncClient()))
        assert tools, "the production tool set must not be empty"
        for tool in tools:
            exposed = walk_property_names(tool.input_schema) & IDENTITY_FIELDS
            assert not exposed, f"{tool.name} exposes {exposed}"

    def test_schemas_lists_each_tool_with_its_flags(self, echo_tool_factory) -> None:  # type: ignore[no-untyped-def]
        build, _ = echo_tool_factory
        registry = need("actions.ToolRegistry")([build(is_write=True)])
        (schema,) = registry.schemas()
        assert schema["name"] == "echo" and schema["is_write"] is True
        assert "input_schema" in schema and "description" in schema


class TestIdentityComesFromThePrincipal:
    async def test_the_handler_receives_the_verified_principal(self, echo_tool_factory) -> None:  # type: ignore[no-untyped-def]
        build, seen = echo_tool_factory
        registry = need("actions.ToolRegistry")([build()])
        principal = make_principal(role=UserRole.USER)
        await registry.invoke("echo", {"month": "2026-10"}, principal)
        assert seen[-1].tenant_id == principal.tenant_id

    async def test_a_tenant_id_in_the_arguments_is_ignored(self, echo_tool_factory) -> None:  # type: ignore[no-untyped-def]
        build, seen = echo_tool_factory
        registry = need("actions.ToolRegistry")([build()])
        principal = make_principal(role=UserRole.USER)
        result = await registry.invoke(
            "echo", {"month": "2026-10", "tenant_id": str(OTHER_TENANT)}, principal
        )
        assert result["tenant"] == str(principal.tenant_id)
        assert seen[-1].tenant_id != OTHER_TENANT

    async def test_a_user_id_in_the_arguments_is_ignored(self, echo_tool_factory) -> None:  # type: ignore[no-untyped-def]
        build, seen = echo_tool_factory
        registry = need("actions.ToolRegistry")([build()])
        principal = make_principal(role=UserRole.USER)
        await registry.invoke("echo", {"month": "x", "user_id": str(uuid4())}, principal)
        assert seen[-1].user_id == principal.user_id


class TestArgumentsAndErrors:
    async def test_an_unknown_tool_is_refused(self, echo_tool_factory) -> None:  # type: ignore[no-untyped-def]
        build, _ = echo_tool_factory
        registry = need("actions.ToolRegistry")([build()])
        with pytest.raises(need("actions.UnknownTool")):
            await registry.invoke("drop_database", {}, make_principal())

    async def test_a_missing_required_argument_is_refused_before_the_handler_runs(
        self, echo_tool_factory
    ) -> None:  # type: ignore[no-untyped-def]
        build, seen = echo_tool_factory
        registry = need("actions.ToolRegistry")([build()])
        with pytest.raises(Exception):  # noqa: B017 - validation error type is the adapter's choice
            await registry.invoke("echo", {}, make_principal())
        assert seen == []

    async def test_a_wrongly_typed_argument_is_refused(self, echo_tool_factory) -> None:  # type: ignore[no-untyped-def]
        build, seen = echo_tool_factory
        registry = need("actions.ToolRegistry")([build()])
        with pytest.raises(Exception):  # noqa: B017
            await registry.invoke("echo", {"month": 12}, make_principal())
        assert seen == []

    async def test_argument_injection_text_is_passed_as_data_only(self, echo_tool_factory) -> None:  # type: ignore[no-untyped-def]
        build, seen = echo_tool_factory
        registry = need("actions.ToolRegistry")([build()])
        await registry.invoke("echo", {"month": "2026-10'; DROP TABLE users; --"}, make_principal())
        assert len(seen) == 1
