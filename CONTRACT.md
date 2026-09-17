# Marking provider contract v1

Distribution `kamiwaza-confidentiality-parser`, import `kamiwaza_confidentiality`.
Python 3.10+. All contract objects are frozen dataclasses. Persist profiles and
marking envelopes with their `to_dict()` / `from_dict()` methods, not
provider-specific Python classes. Levels and displays expose `to_dict()` only.

- `Level(id, name, rank, aliases=(), background_color="#64748b", foreground_color="#ffffff", assignable=True)`
- `Profile(id, revision, levels, defaults={}, identity={})`. `levels` is a tuple of
  Level objects. `defaults` maps operation names (e.g. `document`, `source`,
  `subject`, `site`) to stable level IDs. `identity` holds provider configuration;
  the trusted claim boundary and graph writes belong to the host.
- `NormalizedMarking(profile_id, profile_revision, level_id, raw_text="", attributes={})`
- `Display(text, background_color, foreground_color)` (plain text, hex colors).
- `MarkingProvider` protocol: `contract_version: int = 1`, `profile: Profile`,
  `parse(text: str) -> NormalizedMarking`,
  `validate(marking: NormalizedMarking) -> NormalizedMarking`,
  `present(marking: NormalizedMarking) -> Display`,
  `compose(markings: Sequence[NormalizedMarking], *, context: Mapping[str, Any] | None = None) -> Display | None`.
  Context may carry `surface`, `position`, and host-provided operation context;
  providers must not grant access or mutate the host graph. The reference provider
  uses the highest rank. Other providers own their composition semantics.
- `create_provider(profile: str | Path | Mapping[str, Any] | None = None)` is the
  reference factory. None selects the packaged commercial YAML. Other factories
  use the same positional parameter. A file must be an absolute local path.
- `load_provider(*, enabled: bool, provider: str = "kamiwaza_confidentiality:create_provider", profile: str | Path | Mapping | None = None) -> MarkingProvider | None`.
- `load_from_env(environ: Mapping[str, str] | None = None)`: disabled unless
  `KAMIWAZA_MARKINGS_ENABLED=true`; provider from `KAMIWAZA_MARKINGS_PROVIDER`;
  optional absolute local profile from `KAMIWAZA_MARKINGS_PROFILE`.

Errors: `MarkingError(ValueError)` for bad assignments/envelopes;
`ConfigurationError(ValueError)` for bad profiles/provider loading. An enabled,
missing/incompatible provider never silently falls back. A disabled provider
returns None and does not import optional code. The host must reject operations
on already-marked resources if no compatible provider is enabled.

`Profile.level(value)` resolves stable IDs, names or aliases case-insensitively;
`Profile.rank(value)` returns configured rank. Assignment must reject a level
whose `assignable` is false; presentation-only levels remain listed. Changing
labels/colors does not change stable IDs. Changing policy semantics requires a
new profile revision; providers reject envelopes for other revisions.

YAML shape: `contract_version: 1`, `id`, `revision`, `levels` (list of Level
mappings), optional `defaults` and `identity`. Empty/duplicate/colliding levels,
invalid colors and unknown defaults are configuration errors. The reference
parser only accepts configured exact names/IDs/aliases, never compound grammar.

Stable profile and level IDs use `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}` so they can
serve as portable resource references. Human names and aliases are separate.
Mappings are defensively copied on construction; frozen dataclasses prevent
field reassignment, but callers should still treat nested data as read-only.

An unset or whitespace-only enable flag leaves marking support disabled. Once
enabled, an explicitly empty provider is a configuration error; only an absent
provider setting selects the reference factory.

Provider factories are trusted Python code selected by the deployment
administrator. Loading imports their module and invokes the factory before
validating the resulting object; this is not a sandbox or an authorization
boundary. Never derive the provider selector from untrusted request input.
The loader checks attributes and callable methods directly, consistently across
supported Python versions, including providers exposing members dynamically.
Providers must return this distribution's `Profile` class and depend on a
compatible version of `kamiwaza-confidentiality-parser`.
