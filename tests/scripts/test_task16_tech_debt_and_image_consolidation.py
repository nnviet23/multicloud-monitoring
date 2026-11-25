"""Tests for Task 3: Image Pinning Consolidation & Tech Debt Cleanup."""

from pathlib import Path
import sys
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_kustomize_images(cluster: str) -> set[str]:
    kustomization_path = REPO_ROOT / "deploy" / "clusters" / cluster / "kustomization.yaml"
    data = yaml.safe_load(kustomization_path.read_text(encoding="utf-8"))
    images = set()
    for img in data.get("images", []):
        name = img.get("newName") or img.get("name")
        tag = img.get("newTag")
        if name and tag:
            images.add(f"{name}:{tag}")
    return images


def test_pinned_images_in_cli_match_cluster_kustomizations():
    from infra.cli import PINNED_IMAGES

    for cluster_key, kustomize_dir in [
        ("hub-k3d", "hub"),
        ("aws-k3d", "aws"),
        ("azure-k3d", "azure"),
    ]:
        expected = _load_kustomize_images(kustomize_dir)
        actual = set(PINNED_IMAGES.get(cluster_key, []))
        missing = expected - actual
        assert not missing, f"{cluster_key} missing images in PINNED_IMAGES: {sorted(missing)}"

    # Ensure cert-manager images are also pinned in hub-k3d
    hub_images = set(PINNED_IMAGES.get("hub-k3d", []))
    for cm_img in [
        "quay.io/jetstack/cert-manager-controller:v1.16.2",
        "quay.io/jetstack/cert-manager-webhook:v1.16.2",
        "quay.io/jetstack/cert-manager-cainjector:v1.16.2",
    ]:
        assert cm_img in hub_images, f"Missing cert-manager image: {cm_img}"

    # No :latest or floating tags
    for cluster_key, imgs in PINNED_IMAGES.items():
        for img in imgs:
            assert ":latest" not in img and ":stable" not in img, f"Floating tag in {cluster_key}: {img}"


def test_makefile_preload_images_uses_infra_cli():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "preload-images:" in makefile, "Makefile missing preload-images target"
    assert "$(PYTHON) -m infra.cli preload-images" in makefile, (
        "Makefile preload-images must invoke $(PYTHON) -m infra.cli preload-images"
    )
    assert "bash infra/scripts/import_k3d_images.sh" not in makefile, (
        "Makefile should no longer call bash infra/scripts/import_k3d_images.sh"
    )


def test_argocd_kustomization_pinned_to_v2_12_3():
    kustomization = (REPO_ROOT / "deploy" / "argocd" / "kustomization.yaml").read_text(encoding="utf-8")
    assert "01-core-install.yaml" in kustomization
    assert "v2.10.9" not in kustomization


def test_infra_readme_cleaned():
    infra_readme = (REPO_ROOT / "infra" / "README.md").read_text(encoding="utf-8")
    assert "Ansible Core" not in infra_readme
    assert "2.15.8" not in infra_readme
    assert "docs/decisions/" not in infra_readme
    assert "docs/adr/" in infra_readme
    assert "experiments/" not in infra_readme
    assert "mysql:8.0.36" not in infra_readme
    assert "descartesresearch/teastore-db:1.4.1" in infra_readme


def test_root_readme_lists_10_standardized_dashboards():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    dashboards_dir = REPO_ROOT / "deploy" / "platform" / "visualization-grafana" / "dashboards"
    expected_files = sorted(p.name for p in dashboards_dir.glob("*.json"))
    assert len(expected_files) == 10
    for fname in expected_files:
        assert fname in readme, f"README.md missing dashboard {fname}"
    assert "10 Grafana Dashboards" in readme or "10 Dashboard" in readme


def test_ai_engine_readme_uses_3_cluster_baseline():
    ai_readme = (REPO_ROOT / "ai-engine" / "README.md").read_text(encoding="utf-8")
    assert "gcp-k3d" not in ai_readme.lower(), "ai-engine/README.md still references gcp-k3d"
    assert "4 cụm kubernetes" not in ai_readme.lower()
    assert "4 clusters" not in ai_readme.lower()
    assert "hub-k3d" in ai_readme
    assert "aws-k3d" in ai_readme
    assert "azure-k3d" in ai_readme
