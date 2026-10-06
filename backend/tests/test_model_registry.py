"""
Tests for ml/model_registry.py. Uses a throwaway temp directory for
ARTIFACTS_DIR/REGISTRY_PATH so this never touches the real deployed
model.joblib.
"""
from __future__ import annotations
import json
import pytest


@pytest.fixture
def registry_env(tmp_path, monkeypatch):
    import ml.model_registry as reg
    monkeypatch.setattr(reg, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(reg, "REGISTRY_PATH", tmp_path / "registry.json")
    return reg, tmp_path


def _fake_artifact_pair(tmp_path, tag: str):
    model = tmp_path / f"model_{tag}.joblib"
    model.write_text(f"bytes-{tag}")
    meta = tmp_path / f"meta_{tag}.json"
    meta.write_text(json.dumps({"tag": tag}))
    return model, meta


def test_register_first_version_becomes_active_by_default(registry_env):
    reg, tmp_path = registry_env
    model, meta = _fake_artifact_pair(tmp_path, "a")
    result = reg.register_version("v1.0.0", model, meta)
    assert result["active_version"] == "v1.0.0"


def test_second_version_does_not_auto_activate(registry_env):
    reg, tmp_path = registry_env
    m1, meta1 = _fake_artifact_pair(tmp_path, "a")
    reg.register_version("v1.0.0", m1, meta1, activate=True)
    m2, meta2 = _fake_artifact_pair(tmp_path, "b")
    result = reg.register_version("v1.1.0", m2, meta2, activate=False)
    assert result["active_version"] == "v1.0.0"


def test_activate_version_switches_active_pointer(registry_env):
    reg, tmp_path = registry_env
    m1, meta1 = _fake_artifact_pair(tmp_path, "a")
    reg.register_version("v1.0.0", m1, meta1, activate=True)
    m2, meta2 = _fake_artifact_pair(tmp_path, "b")
    reg.register_version("v1.1.0", m2, meta2)
    reg.activate_version("v1.1.0")
    model_path, _ = reg.get_active_version_paths()
    assert model_path.read_text() == "bytes-b"


def test_rollback_after_activation_restores_prior_version(registry_env):
    reg, tmp_path = registry_env
    m1, meta1 = _fake_artifact_pair(tmp_path, "a")
    reg.register_version("v1.0.0", m1, meta1, activate=True)
    m2, meta2 = _fake_artifact_pair(tmp_path, "b")
    reg.register_version("v1.1.0", m2, meta2, activate=True)
    reg.activate_version("v1.0.0")  # rollback
    model_path, _ = reg.get_active_version_paths()
    assert model_path.read_text() == "bytes-a"


def test_duplicate_version_registration_rejected(registry_env):
    reg, tmp_path = registry_env
    m1, meta1 = _fake_artifact_pair(tmp_path, "a")
    reg.register_version("v1.0.0", m1, meta1)
    with pytest.raises(reg.ModelRegistryError):
        reg.register_version("v1.0.0", m1, meta1)


def test_activating_unknown_version_raises(registry_env):
    reg, tmp_path = registry_env
    m1, meta1 = _fake_artifact_pair(tmp_path, "a")
    reg.register_version("v1.0.0", m1, meta1)
    with pytest.raises(reg.ModelRegistryError):
        reg.activate_version("v9.9.9")


def test_get_active_version_paths_with_no_registry_raises(registry_env):
    reg, tmp_path = registry_env
    with pytest.raises(reg.ModelRegistryError):
        reg.get_active_version_paths()


def test_missing_source_model_file_raises(registry_env):
    reg, tmp_path = registry_env
    _, meta = _fake_artifact_pair(tmp_path, "a")
    with pytest.raises(reg.ModelRegistryError):
        reg.register_version("v1.0.0", tmp_path / "does_not_exist.joblib", meta)
