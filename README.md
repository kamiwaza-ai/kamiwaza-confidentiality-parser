# Kamiwaza confidentiality parser

Small, optional Python marking-provider contract and a configuration-defined
commercial reference implementation. Apache-2.0; Python 3.10 or newer.

Installing the package does not activate marking support. The host application's
normal authorization remains in control. This package neither grants access nor
writes authorization relationships.

```python
from kamiwaza_confidentiality import load_from_env

provider = load_from_env()  # None unless explicitly enabled
if provider is not None:
    marking = provider.parse("Company Private")
    print(marking.to_dict())
    print(provider.present(marking).to_dict())
```

Enable the commercial example explicitly:

```sh
export KAMIWAZA_MARKINGS_ENABLED=true
export KAMIWAZA_MARKINGS_PROVIDER=kamiwaza_confidentiality:create_provider
```

The packaged `profiles/commercial.yaml` defines Public, Company Private and
Company Confidential with stable IDs, ranks, aliases and presentation colors.
It has **no implicit assignment defaults**. Copy it to an absolute local path,
change labels/colors or add configured defaults and select the file:

```sh
export KAMIWAZA_MARKINGS_PROFILE=/etc/kamiwaza/markings.yaml
```

Supported YAML keys and the provider API are documented in [CONTRACT.md](CONTRACT.md).
Exact matching is case-insensitive. Unknown input is rejected; the reference
parser does not interpret compound syntax. Profiles with ambiguous aliases,
invalid colors or invalid defaults fail at load time. No network fetch occurs.
An enabled provider which is missing or incompatible fails explicitly.

Applications must validate stored profile ID/revision and assignments before
using a marking, reject marked operations when the feature is disabled, and
render `Display.text` as plain text. Changing policy semantics requires a new
profile revision. Revision migration, storage, identity trust, authorization,
UI rendering and administrative policy ownership belong to the host.
`Profile.identity` is configuration data only: it never establishes that a user
claim is authentic or grants membership. A specialized provider may validate its
own JSON attributes and implement richer composition without core changes.

## Offline installation

Prepare a wheelhouse on a connected machine with the **same Python/platform** as
the target, including the package wheel and all dependencies:

```sh
python -m pip wheel --wheel-dir wheelhouse .
```

Transfer the wheelhouse through the normal deployment media process, then on the
disconnected target:

```sh
python -m pip install --no-index --find-links=/media/wheelhouse kamiwaza-confidentiality-parser==0.1.0
```

Every selected provider and its dependencies must be present locally. Provider
selection does not install packages, start services or reach a package index.

## Development

```sh
python -m pip install -e '.[test]'
python -m pytest
python -m build
```

This contract deliberately introduces no policy language, background service or
hot reload. Future decision engines can consume the normalized envelope and
trusted host context without changing marking parsing into authorization.
