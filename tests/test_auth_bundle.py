import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "components" / "desktop" / "plugins"

CLONES = {
    "atlas.lock": "omarchy.lock",
    "atlas.polkit": "omarchy.polkit",
    "atlas.idle": "omarchy.idle",
    "atlas.monitor": "omarchy.monitor",
}


def plugin_text(plugin_id: str) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PLUGINS / plugin_id).iterdir())
        if path.is_file()
    )


def test_plugin_manifests_use_portable_atlas_ids_and_provenance():
    for plugin_id, source_id in CLONES.items():
        manifest = json.loads((PLUGINS / plugin_id / "manifest.json").read_text())
        assert manifest["id"] == plugin_id
        assert manifest["omarchy"]["clonedFrom"] == source_id


def test_lock_uses_omarchy_pam_services_without_bundling_pam_policy():
    service = (PLUGINS / "atlas.lock" / "Service.qml").read_text()
    assert 'config: "omarchy-lock-password"' in service
    assert 'config: "omarchy-lock-fingerprint"' in service
    assert 'path: "/etc/pam.d/omarchy-lock-password"' in service
    assert "passwordPamConfigured = text().trim().length > 0" in service
    assert not list(ROOT.rglob("pam.d"))


def test_polkit_has_no_file_based_askpass_secret_bridge():
    text = plugin_text("atlas.polkit")
    forbidden = (
        'target: "askpass"',
        "askpassResultPath",
        "askpassDonePath",
        "atomicWrites",
        "resultFile",
        "doneFile",
    )
    for marker in forbidden:
        assert marker not in text
    assert "PolkitAgent {" in text


def test_polkit_authorization_label_renders_untrusted_message_as_plain_text():
    qml = (PLUGINS / "atlas.polkit" / "PolkitAgent.qml").read_text()
    label = qml[qml.index("id: justificationText") :]
    label = label[: label.index("\n      }")]
    assert 'text: root.authorizationLabel(root.currentMessage).replace(' in label
    assert 'textFormat: Text.PlainText' in label
    assert 'maximumLineCount: 3' in label
    assert 'wrapMode: Text.Wrap' in label
    assert 'clip: true' in label


def test_monitor_does_not_bundle_the_local_hardware_fallback():
    text = plugin_text("atlas.monitor")
    assert "omarchy-brightness-display" in text
    assert "hyprsunset" not in text


def test_auth_plugins_contain_no_password_tempfiles():
    text = plugin_text("atlas.lock") + plugin_text("atlas.polkit")
    assert "mktemp" not in text
    assert "/tmp/" not in text
