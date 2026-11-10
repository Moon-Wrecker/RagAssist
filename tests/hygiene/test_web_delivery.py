"""Slice 6 (ADR 0014): the web container is configured from the environment and serves the app safely.

These tests read the committed nginx templates, the Dockerfile and compose.yaml. They need no Docker daemon; the CI
`web-image` job additionally renders the templates and runs ``nginx -t`` in a throwaway container.
"""

from __future__ import annotations

import re

import pytest
import yaml
from dotenv import dotenv_values
from support.repo import REPO_ROOT, active_lines, read

pytestmark = pytest.mark.hygiene

TEMPLATE_DIR = REPO_ROOT / "infra" / "nginx" / "templates"
SERVER = "infra/nginx/templates/default.conf.template"
SECURITY = "infra/nginx/templates/security-headers.inc.template"
PROXY = "infra/nginx/templates/proxy.inc.template"
ENVSH = "infra/nginx/15-web-env.envsh"
DOCKERFILE = "infra/docker/web.Dockerfile"
# Variables the web service takes from .env. Not Settings fields: only compose and nginx read them.
WEB_VARIABLES = {"WEB_PORT", "WEB_SERVER_NAME", "WEB_API_UPSTREAM", "WEB_HSTS"}


def code_lines(relative: str) -> list[str]:
    """Directive lines without comments or blanks."""
    return [
        line.strip()
        for line in read(relative).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def location_blocks(relative: str) -> dict[str, str]:
    """Map each ``location`` header (``= /v1/events``) to its body, matching braces."""
    text = "\n".join(code_lines(relative))
    blocks: dict[str, str] = {}
    for match in re.finditer(r"location\s+([^{]+?)\s*\{", text):
        depth, i = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        blocks[match.group(1)] = text[match.end() : i - 1]
    return blocks


def directive(block: str, name: str) -> str | None:
    found = re.search(rf"^{name}\s+(.+?);", block, re.M)
    return found.group(1) if found else None


def seconds(value: str) -> int:
    return int(value.rstrip("s"))


SSE_LOCATIONS = ["= /v1/events", "~ ^/v1/conversations/[^/]+/messages$"]


class TestFilesAreLinuxFriendly:
    @pytest.mark.parametrize(
        "relative", [SERVER, SECURITY, PROXY, ENVSH, DOCKERFILE, DOCKERFILE + ".dockerignore"]
    )
    def test_file_uses_lf(self, relative: str) -> None:
        assert b"\r" not in (REPO_ROOT / relative).read_bytes(), f"{relative} has CRLF"

    def test_gitattributes_forces_lf_on_nginx_files(self) -> None:
        rules = {line.split()[0]: line.split()[1:] for line in active_lines(".gitattributes")}
        for pattern in (
            "infra/nginx/** text eol=lf",
            "*.template text eol=lf",
            "*.envsh text eol=lf",
        ):
            name, *attrs = pattern.split()
            assert set(attrs) <= set(rules.get(name, [])), f".gitattributes needs `{pattern}`"


class TestNothingDeploymentSpecificIsWrittenDown:
    def test_listen_port_server_name_and_upstream_come_from_variables(self) -> None:
        server = code_lines(SERVER)
        listens = [line for line in server if line.startswith("listen ")]
        assert listens and all(re.match(r"listen \$\{WEB_PORT\}[ ;]", line) for line in listens)
        names = [line for line in server if line.startswith("server_name ")]
        assert names == ["server_name ${WEB_SERVER_NAME};"]
        assert "proxy_pass http://${WEB_API_UPSTREAM};" in code_lines(PROXY)

    @pytest.mark.parametrize("relative", [SERVER, SECURITY, PROXY])
    def test_no_host_address_or_port_literal(self, relative: str) -> None:
        for line in code_lines(relative):
            stripped = re.sub(r"\$\{[A-Z_]+\}", "", line)
            assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", stripped), line
            assert not re.search(r"localhost|\bapi:\d|host\.docker", stripped), line
            assert not re.search(r"(listen|proxy_pass|server)\s[^;]*:\d{2,5}", stripped), line

    def test_every_substituted_variable_is_known_and_documented(self) -> None:
        used: set[str] = set()
        for relative in (SERVER, SECURITY, PROXY):
            used |= set(re.findall(r"\$\{([A-Z_]+)\}", "\n".join(code_lines(relative))))
        assert used == WEB_VARIABLES
        example = dotenv_values(REPO_ROOT / ".env.example")
        assert set(example) >= WEB_VARIABLES

    def test_the_entrypoint_check_covers_every_required_variable(self) -> None:
        text = read(ENVSH)
        assert "WEB_PORT WEB_SERVER_NAME WEB_API_UPSTREAM" in text
        assert 'export WEB_HSTS="${WEB_HSTS-}"' in text, "optional variables must still be defined"

    def test_the_dockerfile_bakes_in_no_port_or_address(self) -> None:
        lines = code_lines(DOCKERFILE)
        assert not [line for line in lines if re.match(r"(EXPOSE|ENV)\b", line)], lines
        assert not [line for line in lines if re.search(r"localhost|127\.0\.0\.1|:\d{4,5}\b", line)]


class TestStreamingLocationsAreNotBuffered:
    @pytest.mark.parametrize("header", SSE_LOCATIONS)
    def test_sse_location_streams(self, header: str) -> None:
        block = location_blocks(SERVER)[header]
        assert directive(block, "proxy_buffering") == "off"
        assert directive(block, "gzip") == "off"
        assert directive(block, "proxy_cache") == "off"
        assert seconds(directive(block, "proxy_read_timeout") or "0") >= 3600
        assert "include /etc/nginx/conf.d/proxy.inc;" in block
        assert 'add_header X-Accel-Buffering "no" always;' in block

    def test_proxy_settings_are_valid_for_streaming_and_forward_the_client(self) -> None:
        proxy = "\n".join(code_lines(PROXY))
        assert "proxy_http_version 1.1;" in proxy
        assert 'proxy_set_header Connection "";' in proxy
        for header in ("X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host"):
            assert f"proxy_set_header {header} " in proxy
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in proxy, (
            "the edge proxy overwrites X-Forwarded-For so a client cannot pick its throttle key"
        )

    def test_text_event_stream_is_never_compressed(self) -> None:
        types = directive("\n".join(code_lines(SERVER)), "gzip_types") or ""
        assert "text/event-stream" not in types
        assert "text/css" in types and "javascript" in types

    def test_every_api_location_proxies_and_declines_compression(self) -> None:
        blocks = location_blocks(SERVER)
        api = {h: b for h, b in blocks.items() if "/v1/" in h or h == "= /healthz"}
        assert len(api) >= 5
        for header, block in api.items():
            assert "proxy.inc" in block, header
            assert directive(block, "gzip") == "off", header

    def test_only_the_upload_route_takes_a_large_body(self) -> None:
        blocks = location_blocks(SERVER)
        upload = directive(blocks["= /v1/documents"], "client_body_timeout")
        assert upload is not None
        size = directive(blocks["= /v1/documents"], "client_max_body_size")
        assert size is not None and int(size.rstrip("m")) >= 50, "the API accepts up to 50 MiB"
        server_level = re.search(
            r"^client_max_body_size (\S+);", "\n".join(code_lines(SERVER)), re.M
        )
        assert server_level and int(server_level.group(1).rstrip("m")) <= 2


class TestSpaAndCaching:
    def test_unknown_routes_fall_back_to_the_app_but_missing_assets_do_not(self) -> None:
        blocks = location_blocks(SERVER)
        assert "try_files $uri /index.html;" in blocks["/"]
        assert "try_files $uri =404;" in blocks["/assets/"]

    def test_hashed_assets_are_immutable_and_the_shell_is_revalidated(self) -> None:
        blocks = location_blocks(SERVER)
        assert (
            'add_header Cache-Control "public, max-age=31536000, immutable";' in blocks["/assets/"]
        ), "no `always`: a 404 for an asset must never be cached for a year"
        assert 'add_header Cache-Control "no-cache" always;' in blocks["/"]

    def test_dotfiles_are_denied_and_the_server_is_quiet(self) -> None:
        blocks = location_blocks(SERVER)
        assert "return 404;" in blocks["~ /\\."]
        assert "server_tokens off;" in code_lines(SERVER)

    def test_every_content_location_sends_the_security_headers(self) -> None:
        for header, block in location_blocks(SERVER).items():
            if header == "= /web-healthz":
                continue
            assert "include /etc/nginx/conf.d/security-headers.inc;" in block, header


class TestSecurityHeaders:
    def header(self, name: str) -> str:
        found = re.search(rf'add_header {name} "([^"]*)" always;', read(SECURITY))
        assert found, f"{name} is not set"
        return found.group(1)

    def test_csp_allows_only_what_the_app_needs(self) -> None:
        directives = {
            d.split()[0]: d.split()[1:]
            for d in (part.strip() for part in self.header("Content-Security-Policy").split(";"))
            if d
        }
        assert directives["default-src"] == ["'none'"]
        assert directives["script-src"] == ["'self'"], (
            "no inline script, no eval, no third-party script"
        )
        assert directives["frame-ancestors"] == ["'none'"]
        assert directives["object-src"] == ["'none'"]
        assert directives["base-uri"] == ["'none'"]
        assert directives["connect-src"] == ["'self'"]
        assert directives["font-src"] == ["'self'"]
        everything = self.header("Content-Security-Policy")
        assert "*" not in everything and "http:" not in everything and "https:" not in everything
        assert "unsafe-eval" not in everything
        assert "unsafe-inline" not in " ".join(directives["script-src"])

    def test_index_html_needs_no_inline_script_or_remote_resource(self) -> None:
        html = read("frontend/index.html")
        scripts = re.findall(r"<script\b([^>]*)>", html)
        assert scripts and all("src=" in attrs for attrs in scripts), (
            "an inline script breaks the CSP"
        )
        assert not re.search(r"(src|href)=[\"']https?://", html), "a remote resource breaks the CSP"
        assert not re.search(r"\son[a-z]+=[\"']", html), "inline event handlers break the CSP"

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("Cross-Origin-Opener-Policy", "same-origin"),
        ],
    )
    def test_fixed_headers(self, name: str, value: str) -> None:
        assert self.header(name) == value

    def test_permissions_policy_turns_off_powerful_features(self) -> None:
        policy = self.header("Permissions-Policy")
        for feature in ("camera", "microphone", "geolocation"):
            assert f"{feature}=()" in policy

    def test_hsts_is_only_sent_when_the_operator_sets_it(self) -> None:
        assert self.header("Strict-Transport-Security") == "${WEB_HSTS}"
        assert "max-age" not in "\n".join(code_lines(SECURITY)), (
            "HSTS over plain HTTP is ignored at best and pins a dev host at worst: it comes from WEB_HSTS only"
        )


class TestDockerfile:
    def test_multi_stage_build_with_a_locked_install_and_the_ci_build(self) -> None:
        lines = code_lines(DOCKERFILE)
        froms = [line for line in lines if line.startswith("FROM ")]
        assert len(froms) == 2 and froms[0].endswith("AS build")
        assert "RUN npm ci" in lines
        assert "RUN npm run build" in lines
        assert any(line.startswith("COPY --from=build /app/dist/") for line in lines)
        assert "tsc --noEmit && vite build" in read("frontend/package.json"), (
            "`npm run build` is the type-check plus the production build"
        )

    def test_images_are_pinned(self) -> None:
        args = dict(
            line.removeprefix("ARG ").split("=", 1)
            for line in code_lines(DOCKERFILE)
            if line.startswith("ARG ")
        )
        node, nginx = args["NODE_IMAGE"], args["NGINX_IMAGE"]
        assert re.fullmatch(r"node:(2[2-9]|[3-9]\d)(\.\d+)*(-alpine)?", node), node
        assert re.fullmatch(r"nginx/nginx-unprivileged:\d+\.\d+\.\d+(-alpine)?", nginx), nginx
        for image in (node, nginx):
            assert not image.endswith((":latest", ":stable", ":mainline"))

    def test_node_matches_the_engine_the_app_declares(self) -> None:
        assert '"node": ">=22"' in read("frontend/package.json")

    def test_runs_without_root_through_the_template_mechanism(self) -> None:
        text = read(DOCKERFILE)
        assert "nginx-unprivileged" in text
        assert "COPY infra/nginx/templates/ /etc/nginx/templates/" in text
        assert "USER root" not in text


class TestBuildContext:
    @pytest.mark.parametrize(
        "entry",
        [
            "frontend/node_modules",
            "frontend/dist",
            "frontend/screenshots",
            "frontend/test-results",
            "frontend/playwright-report",
        ],
    )
    def test_web_context_excludes(self, entry: str) -> None:
        assert entry in active_lines(DOCKERFILE + ".dockerignore")

    def test_web_context_is_an_allow_list(self) -> None:
        lines = active_lines(DOCKERFILE + ".dockerignore")
        assert lines[0] == "*" and "!frontend/" in lines and "!infra/nginx/" in lines
        assert ".env" not in " ".join(
            line for line in lines if line.startswith("!") and "example" not in line
        )

    @pytest.mark.parametrize(
        "entry",
        ["frontend/node_modules", "frontend/dist", "frontend/screenshots", "frontend/test-results"],
    )
    def test_root_dockerignore_keeps_local_frontend_output_out(self, entry: str) -> None:
        lines = {line.rstrip("/") for line in active_lines(".dockerignore")}
        assert entry in lines or "frontend" in lines

    @pytest.mark.parametrize(
        "entry", ["frontend/screenshots/", "frontend/test-results/", "frontend/dist/"]
    )
    def test_gitignore_covers_frontend_output(self, entry: str) -> None:
        assert entry in active_lines(".gitignore")


@pytest.fixture(scope="module")
def services() -> dict[str, dict]:
    return yaml.safe_load(read("compose.yaml"))["services"]


class TestCompose:
    def test_web_service_is_wired_like_the_others(self, services: dict[str, dict]) -> None:
        web = services["web"]
        assert web["build"]["dockerfile"] == DOCKERFILE
        assert web["build"]["context"] == "."
        assert web["restart"] == "unless-stopped"
        assert web["depends_on"]["api"] == {"condition": "service_healthy", "restart": True}
        assert "healthcheck" in web and "healthcheck" in services["api"]

    def test_web_values_come_from_the_environment(self, services: dict[str, dict]) -> None:
        env = services["web"]["environment"]
        assert set(env) == WEB_VARIABLES
        assert all(re.fullmatch(r"\$\{WEB_[A-Z_]+(:\?[^}]*|-)\}", str(v)) for v in env.values()), (
            env
        )
        port = services["web"]["ports"][0]
        assert port.startswith("127.0.0.1:${WEB_PORT:?"), (
            "publish on loopback only; TLS and exposure are a deliberate step"
        )
        assert re.search(r"\$\{WEB_PORT:\?[^}]*\}$", port)

    def test_the_api_is_served_behind_the_proxy(self, services: dict[str, dict]) -> None:
        # `ragassist serve` passes TRUSTED_PROXY_IPS to uvicorn (tests/unit/test_cli_serve.py); compose must not
        # override it with a literal, so it stays an operator decision in .env.
        api_env = services["api"].get("environment", {})
        assert "TRUSTED_PROXY_IPS" not in api_env and "FORWARDED_ALLOW_IPS" not in api_env
        assert "TRUSTED_PROXY_IPS" in dotenv_values(REPO_ROOT / ".env.example")
