import json
from dataclasses import replace

import pytest

from kamiwaza_confidentiality import (
    ConfigurationError,
    ConfiguredProvider,
    Display,
    Level,
    MarkingError,
    NormalizedMarking,
    Profile,
    create_provider,
    load_from_env,
    load_provider,
)


def test_disabled_never_imports_provider_or_reads_profile():
    assert (
        load_provider(enabled=False, provider="missing:factory", profile="/missing")
        is None
    )
    assert load_from_env({}) is None


def test_enabled_commercial_exact_matching_and_roundtrip():
    provider = load_from_env({"KAMIWAZA_MARKINGS_ENABLED": "true"})
    marking = provider.parse(" private ")
    assert marking.level_id == "private"
    assert marking.raw_text == " private "
    assert provider.present(marking).text == "Company Private"
    assert (
        NormalizedMarking.from_dict(json.loads(json.dumps(marking.to_dict())))
        == marking
    )
    assert Profile.from_dict(provider.profile.to_dict()) == provider.profile


@pytest.mark.parametrize(
    "text", ["", "nonsense", "Public / Private", "Public; Private", None]
)
def test_unknown_or_compound_text_rejected(text):
    with pytest.raises(MarkingError):
        create_provider().parse(text)


def test_config_override_changes_vocabulary_without_changing_contract(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("""contract_version: 1
id: example
revision: "v2"
levels:
  - {id: shared, name: Shared, rank: 7, aliases: [Team]}
defaults: {document: shared}
identity: {attribute: access_level}
""")
    provider = load_provider(enabled=True, profile=path)
    assert provider.parse("Team").level_id == "shared"
    assert provider.profile.defaults["document"] == "shared"
    assert provider.profile.identity["attribute"] == "access_level"
    with pytest.raises(MarkingError):
        provider.parse("public")


@pytest.mark.parametrize(
    "provider,profile",
    [
        ("missing:factory", None),
        ("malformed", None),
        ("json:loads", None),
        ("kamiwaza_confidentiality:create_provider", "/nonexistent"),
        ("kamiwaza_confidentiality:create_provider", "relative.yaml"),
    ],
)
def test_enabled_loader_never_falls_back(provider, profile):
    with pytest.raises(ConfigurationError):
        load_provider(enabled=True, provider=provider, profile=profile)


@pytest.mark.parametrize(
    "change",
    [
        {"profile_id": "other"},
        {"profile_revision": "2"},
        {"level_id": "Public"},
        {"attributes": {"unexpected": ["value"]}},
    ],
)
def test_reject_foreign_envelope_and_undefined_attributes(change):
    provider = create_provider()
    with pytest.raises(MarkingError):
        provider.validate(replace(provider.parse("public"), **change))


def test_presentation_only_level_does_not_become_assignable():
    provider = ConfiguredProvider(
        Profile(
            "demo",
            "1",
            (
                Level("low", "Low", 0),
                Level("display", "Display", 1, assignable=False),
            ),
        )
    )
    with pytest.raises(MarkingError):
        provider.parse("Display")
    marking = NormalizedMarking("demo", "1", "display")
    assert provider.present(marking).text == "Display"
    assert provider.compose([provider.parse("Low"), marking]).text == "Display"


def test_composition_rank_is_configuration_defined():
    provider = create_provider()
    markings = [
        provider.parse("private"),
        provider.parse("public"),
        provider.parse("confidential"),
    ]
    assert (
        provider.compose(markings, context={"position": "top"}).text
        == "Company Confidential"
    )
    assert provider.compose([]) is None
    with pytest.raises(MarkingError):
        provider.compose([replace(markings[0], profile_revision="other")])


@pytest.mark.parametrize(
    "levels",
    [
        [],
        [Level("one", "One", 1), Level("two", "Two", 1)],
        [Level("one", "One", 1), Level("two", "Two", 2, aliases=("ONE",))],
        [Level("one", "One", 1), Level("one", "Other", 2)],
    ],
)
def test_ambiguous_or_empty_profiles_rejected(levels):
    with pytest.raises(ConfigurationError):
        Profile("demo", "1", levels)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"contract_version": 2},
        {
            "contract_version": 1,
            "id": "demo",
            "revision": "1",
            "levels": [{"id": "x", "name": "X", "rank": 0}],
            "defaults": {"document": "missing"},
        },
        {
            "contract_version": 1,
            "id": "demo",
            "revision": "1",
            "levels": [{"id": "x", "name": "X", "rank": 0}],
            "unknown": True,
        },
    ],
)
def test_invalid_configuration_rejected(document):
    with pytest.raises(ConfigurationError):
        create_provider(document)


@pytest.mark.parametrize(
    "color", ["red", "url(https://example.com)", "#fff", "#zzzzzz"]
)
def test_presentation_colors_are_inert(color):
    with pytest.raises(ConfigurationError):
        Display("Example", color, "#ffffff")


def test_non_json_attributes_rejected():
    with pytest.raises(MarkingError):
        NormalizedMarking("demo", "1", "x", attributes={"value": float("nan")})
    with pytest.raises(MarkingError):
        NormalizedMarking("demo", "1", "x", attributes={"value": object()})


def test_invalid_enabled_flag_rejected():
    with pytest.raises(ConfigurationError):
        load_from_env({"KAMIWAZA_MARKINGS_ENABLED": "sometimes"})


@pytest.mark.parametrize(
    "identifier", ["has spaces", "group/path", "../path", "", "x" * 129]
)
def test_identifiers_are_portable_but_names_remain_human(identifier):
    with pytest.raises(ConfigurationError):
        Level(identifier, "Human Readable Name", 0)
    with pytest.raises(ConfigurationError):
        Profile(identifier, "1", [Level("valid", "Human Readable Name", 0)])
    with pytest.raises(MarkingError):
        NormalizedMarking("valid", "1", identifier)


def test_boolean_is_not_contract_version():
    document = create_provider().profile.to_dict()
    document["contract_version"] = True
    with pytest.raises(ConfigurationError):
        create_provider(document)


def test_nested_envelope_attributes_detached_from_caller():
    attrs = {"labels": ["one"]}
    marking = NormalizedMarking("profile", "1", "level", attributes=attrs)
    attrs["labels"].append("two")
    assert marking.attributes == {"labels": ["one"]}


@pytest.mark.parametrize("key", [1, True, None, 1.5, ("key",)])
@pytest.mark.parametrize("depth", ["object", "array", "nested"])
def test_nested_non_string_object_keys_rejected(key, depth):
    invalid = {key: "original", str(key): "collision"}
    attributes = {
        "object": {"values": invalid},
        "array": {"values": [invalid]},
        "nested": {"values": [{"deeper": [[invalid]]}]},
    }[depth]
    with pytest.raises(MarkingError, match="string keys"):
        NormalizedMarking("profile", "1", "level", attributes=attributes)
    with pytest.raises(ConfigurationError, match="string keys"):
        Profile("profile", "1", [Level("level", "Level", 0)], identity=attributes)


def test_nested_json_attributes_preserved_and_detached():
    attributes = {"values": [{"1": [None, True, 1, 1.5, {"label": "one"}]}]}
    marking = NormalizedMarking("profile", "1", "level", attributes=attributes)
    assert marking.attributes == attributes
    attributes["values"][0]["1"][-1]["label"] = "two"
    assert marking.attributes["values"][0]["1"][-1] == {"label": "one"}


def test_circular_attributes_rejected():
    attributes = {"values": []}
    attributes["values"].append(attributes)
    with pytest.raises(MarkingError, match="JSON values"):
        NormalizedMarking("profile", "1", "level", attributes=attributes)


def test_provider_with_noncallable_methods_is_incompatible(monkeypatch):
    import types

    import kamiwaza_confidentiality as package

    fake_provider = types.SimpleNamespace(
        contract_version=1,
        profile=create_provider().profile,
        parse=1,
        validate=1,
        present=1,
        compose=1,
    )
    module = types.SimpleNamespace(factory=lambda profile: fake_provider)
    monkeypatch.setattr(package.importlib, "import_module", lambda name: module)
    with pytest.raises(ConfigurationError):
        load_provider(enabled=True, provider="fake:factory")


@pytest.mark.parametrize("value", ["", "  "])
def test_empty_enable_flag_stays_disabled(value):
    assert load_from_env({"KAMIWAZA_MARKINGS_ENABLED": value}) is None


@pytest.mark.parametrize("value", ["", "  "])
def test_enabled_empty_provider_is_explicit_error(value):
    with pytest.raises(ConfigurationError, match="nonempty provider"):
        load_from_env(
            {"KAMIWAZA_MARKINGS_ENABLED": "true", "KAMIWAZA_MARKINGS_PROVIDER": value}
        )


def test_profile_bad_encoding_is_configuration_error(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_bytes(b"\xff")
    with pytest.raises(ConfigurationError, match="Unable to load marking profile"):
        create_provider(path)


def test_profile_null_path_is_configuration_error():
    with pytest.raises(ConfigurationError, match="Unable to load marking profile"):
        create_provider("/bad\0.yaml")


def test_profile_export_detaches_nested_identity():
    profile = Profile(
        "profile",
        "1",
        [Level("level", "Level", 0)],
        identity={"claims": [{"names": ["one"]}]},
    )
    exported = profile.to_dict()
    exported["identity"]["claims"][0]["names"].append("two")
    assert profile.identity == {"claims": [{"names": ["one"]}]}


def test_dynamic_provider_contract_loaded_consistently(monkeypatch):
    import types

    import kamiwaza_confidentiality as package

    delegate = create_provider()

    class DynamicProvider:
        def __init__(self):
            self.delegate = delegate

        def __getattr__(self, name):
            return getattr(self.delegate, name)

    monkeypatch.setattr(
        package.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(factory=lambda profile: DynamicProvider()),
    )
    provider = load_provider(enabled=True, provider="external:factory")
    marking = provider.validate(provider.parse("private"))
    assert provider.present(marking).text == "Company Private"
    assert provider.compose([marking]).text == "Company Private"


@pytest.mark.parametrize("change", [{"contract_version": 2}, {"profile": {}}])
def test_wrong_provider_contract_rejected(monkeypatch, change):
    import types

    import kamiwaza_confidentiality as package

    provider = create_provider()
    for name, value in change.items():
        setattr(provider, name, value)
    monkeypatch.setattr(
        package.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(factory=lambda profile: provider),
    )
    with pytest.raises(ConfigurationError):
        load_provider(enabled=True, provider="external:factory")


def test_deep_json_values_raise_typed_errors():
    import sys

    values = []
    for _ in range(max(20_000, sys.getrecursionlimit() * 2)):
        values = [values]
    attributes = {"values": values}
    with pytest.raises(MarkingError, match="JSON values"):
        NormalizedMarking("profile", "1", "level", attributes=attributes)
    with pytest.raises(MarkingError, match="JSON values"):
        NormalizedMarking.from_dict(
            {
                "profile_id": "profile",
                "profile_revision": "1",
                "level_id": "level",
                "attributes": attributes,
            }
        )
    with pytest.raises(ConfigurationError, match="JSON values"):
        Profile("profile", "1", [Level("level", "Level", 0)], identity=attributes)


def test_deep_yaml_raises_configuration_error(tmp_path):
    import sys

    depth = sys.getrecursionlimit() + 100
    path = tmp_path / "profile.yaml"
    path.write_text("identity: " + "[" * depth + "0" + "]" * depth)
    with pytest.raises(ConfigurationError, match="Unable to load marking profile"):
        create_provider(path)


def test_top_level_mapping_is_snapshotted_once_before_validation():
    from collections.abc import Mapping

    class OneReadMapping(Mapping):
        def __init__(self):
            self.iterations = 0
            self.reads = 0

        def __iter__(self):
            self.iterations += 1
            assert self.iterations == 1, "Mapping was materialized again"
            return iter(["label"])

        def __getitem__(self, key):
            self.reads += 1
            assert self.reads == 1, "Mapping value was read again"
            return ["Public"]

        def __len__(self):
            return 1

    value = OneReadMapping()
    marking = NormalizedMarking("profile", "1", "level", attributes=value)
    assert marking.attributes == {"label": ["Public"]}
    assert (value.iterations, value.reads) == (1, 1)


@pytest.mark.parametrize(
    "label,query", [("Café", " CAFE\u0301 "), ("Straße", "STRASSE")]
)
def test_canonical_unicode_alias_matching_preserves_text(label, query):
    provider = ConfiguredProvider(Profile("profile", "1", [Level("level", label, 0)]))
    marking = provider.parse(query)
    assert marking.level_id == "level"
    assert marking.raw_text == query
    assert provider.present(marking).text == label
    assert provider.profile.to_dict()["levels"][0]["name"] == label


@pytest.mark.parametrize("alias", ["Cafe\u0301", " CAFE\u0301 "])
def test_canonically_equivalent_aliases_cannot_select_different_levels(alias):
    with pytest.raises(ConfigurationError, match="Ambiguous"):
        Profile(
            "profile",
            "1",
            [Level("one", "Café", 0), Level("two", "Other", 1, aliases=(alias,))],
        )
