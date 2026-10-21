"""Keep audited TLS/trust-store and optional image dependencies patched."""

import tomllib
from pathlib import Path

from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]


def test_rust_tls_lock_uses_patched_verifier_and_trust_store():
    packages = tomllib.loads((ROOT / 'Cargo.lock').read_text())['package']
    verifiers = [p for p in packages if p['name'] == 'rustls-webpki']
    roots = [p for p in packages if p['name'] == 'webpki-roots']
    assert verifiers and roots
    assert all(Version('0.103.16') <= Version(p['version']) < Version('0.104') for p in verifiers)
    parents = [p for p in roots if Version(p['version']).major == 1]
    assert parents and all(Version(p['version']) >= Version('1.0.10') for p in parents)
    for package in roots:
        if Version(package['version']).major != 1:
            assert package['version'] == '0.26.11'
            assert all('webpki-roots ' + p['version'] in package['dependencies'] for p in parents)


def test_python_lock_uses_patched_ca_bundle():
    packages = tomllib.loads((ROOT / 'uv.lock').read_text())['package']
    for name, minimum in [('certifi', '2026.10.19')]:
        matches = [p for p in packages if p['name'] == name]
        assert matches, name
        assert all(Version(p['version']) >= Version(minimum) for p in matches), name
