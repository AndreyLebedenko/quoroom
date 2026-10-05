import re
import tomllib
import unittest
from pathlib import Path

import yaml

from sessionchat.installer.server import (
    IMAGE,
    SERVER_NAME,
    TOML_KEY,
    toml_place,
    toml_value,
)

# english-release-16: the templates carry English comments and mean the same

REPO = Path(__file__).resolve().parent.parent.parent
DOCKER = REPO / "docker"
ENV_EXAMPLE = DOCKER / ".env.example"
TOML_EXAMPLE = DOCKER / "continuwuity" / "continuwuity.toml.example"
CADDYFILE = DOCKER / "caddy" / "Caddyfile"
COMPOSE = DOCKER / "docker-compose.yml"
TEMPLATES = (ENV_EXAMPLE, TOML_EXAMPLE, CADDYFILE, COMPOSE)
CYRILLIC = re.compile("[Ѐ-ӿ]")
EXAMPLE_TOKEN = "change-me-before-first-run"
IMAGES = [
    "ghcr.io/continuwuity/continuwuity:latest",
    "vectorim/element-web:latest",
    "caddy:2-alpine",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class EnglishTemplateTests(unittest.TestCase):
    def test_no_template_has_cyrillic(self):
        for path in TEMPLATES:
            with self.subTest(template=path.name):
                self.assertIsNone(CYRILLIC.search(read(path)))

    def test_every_template_is_printable_ascii(self):
        for path in TEMPLATES:
            for number, line in enumerate(read(path).splitlines(), 1):
                with self.subTest(template=path.name, line=number):
                    self.assertRegex(line, r"^[\t\x20-\x7e]*$")

    def test_every_template_still_explains_itself_in_comments(self):
        for path in TEMPLATES:
            with self.subTest(template=path.name):
                comments = [line for line in read(path).splitlines() if "#" in line]
                self.assertGreater(len(comments), 0)


class EnvTemplateTests(unittest.TestCase):
    def assignments(self) -> dict[str, str]:
        found = {}
        for line in read(ENV_EXAMPLE).splitlines():
            if line.strip() and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                found[key.strip()] = value.strip()
        return found

    def test_the_installer_finds_the_server_name_it_checks(self):
        lines = [
            line
            for line in read(ENV_EXAMPLE).splitlines()
            if line.strip().startswith("SERVER_NAME=")
        ]
        self.assertEqual(lines, [f"SERVER_NAME={SERVER_NAME}"])

    def test_the_only_setting_is_the_server_name(self):
        self.assertEqual(self.assignments(), {"SERVER_NAME": SERVER_NAME})


class TomlTemplateTests(unittest.TestCase):
    def lines(self) -> list[str]:
        return read(TOML_EXAMPLE).splitlines()

    def test_the_installer_reads_the_same_keys_from_the_example(self):
        self.assertEqual(toml_value(self.lines(), "allow_registration")[0], "true")
        self.assertEqual(
            toml_value(self.lines(), "registration_token")[0], EXAMPLE_TOKEN
        )

    def test_the_installer_sees_no_other_key_in_the_example(self):
        keys = [
            match.group(1)
            for match in map(TOML_KEY.match, self.lines())
            if match is not None
        ]
        self.assertEqual(keys, ["allow_registration", "registration_token"])

    def test_the_installer_replaces_only_the_token_line(self):
        placed = toml_place(self.lines(), "registration_token", '"issued"')
        changed = [
            (before, after)
            for before, after in zip(self.lines(), placed, strict=True)
            if before != after
        ]
        self.assertEqual(
            changed,
            [
                (
                    f'registration_token = "{EXAMPLE_TOKEN}"',
                    'registration_token = "issued"',
                )
            ],
        )

    def test_the_example_is_valid_toml_with_its_keys_inside_the_global_section(self):
        parsed = tomllib.loads(read(TOML_EXAMPLE))
        self.assertEqual(
            parsed,
            {
                "global": {
                    "allow_registration": True,
                    "registration_token": EXAMPLE_TOKEN,
                }
            },
        )


class ComposeTemplateTests(unittest.TestCase):
    def parsed(self) -> dict:
        return yaml.safe_load(read(COMPOSE))

    def test_the_installer_finds_the_same_images(self):
        self.assertEqual(list(dict.fromkeys(IMAGE.findall(read(COMPOSE)))), IMAGES)

    def test_the_stack_has_the_same_services(self):
        self.assertEqual(
            set(self.parsed()["services"]), {"continuwuity", "element", "caddy"}
        )

    def test_the_server_is_configured_for_a_local_stand_without_federation(self):
        environment = self.parsed()["services"]["continuwuity"]["environment"]
        self.assertEqual(
            environment,
            {
                "CONTINUWUITY_SERVER_NAME": "${SERVER_NAME}",
                "CONTINUWUITY_DATABASE_PATH": "/var/lib/continuwuity",
                "CONTINUWUITY_ADDRESS": "0.0.0.0",
                "CONTINUWUITY_PORT": 8008,
                "CONTINUWUITY_CONFIG": "/etc/continuwuity/continuwuity.toml",
                "CONTINUWUITY_ALLOW_FEDERATION": "false",
                "CONTINUWUITY_ALLOW_CHECK_FOR_UPDATES": "false",
                "CONTINUWUITY_LOG": "info",
            },
        )

    def test_only_https_is_published_to_the_host(self):
        self.assertEqual(self.parsed()["services"]["caddy"]["ports"], ["443:443"])

    def test_the_config_files_are_mounted_read_only(self):
        services = self.parsed()["services"]
        self.assertIn(
            "./continuwuity/continuwuity.toml:/etc/continuwuity/continuwuity.toml:ro",
            services["continuwuity"]["volumes"],
        )
        self.assertIn(
            "./caddy/Caddyfile:/etc/caddy/Caddyfile:ro", services["caddy"]["volumes"]
        )
        self.assertIn(
            "./element/config.json:/app/config.json:ro",
            services["element"]["volumes"],
        )

    def test_the_named_volumes_that_keep_the_data_are_declared(self):
        self.assertEqual(
            set(self.parsed()["volumes"]),
            {"continuwuity-data", "caddy-data", "caddy-config"},
        )


class CaddyfileTests(unittest.TestCase):
    def directives(self) -> list[str]:
        return [
            line.strip()
            for line in read(CADDYFILE).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_the_site_terminates_tls_with_the_local_certificate(self):
        self.assertEqual(self.directives()[0], "agentschat.local {")
        self.assertIn(
            "tls /certs/agentschat.local.pem /certs/agentschat.local-key.pem",
            self.directives(),
        )

    def test_matrix_traffic_goes_to_the_server_and_the_rest_to_element(self):
        self.assertEqual(
            self.directives()[2:],
            [
                "@matrix path /_matrix/* /_continuwuity/* /.well-known/matrix/*",
                "handle @matrix {",
                "reverse_proxy continuwuity:8008",
                "}",
                "handle {",
                "reverse_proxy element:80",
                "}",
                "}",
            ],
        )


if __name__ == "__main__":
    unittest.main()
