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
