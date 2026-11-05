from pathlib import Path
import shutil
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "agentforge"


def test_edge_gateway_values_and_templates_exist() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    assert values["edgeGateway"]["enabled"] is False
    assert values["edgeGateway"]["gatewayClassName"] == "eg"
    assert (CHART / "templates" / "gateway.yaml").exists()
    assert (CHART / "templates" / "httproute.yaml").exists()


def test_helm_renders_gateway_resources_when_enabled() -> None:
    helm = shutil.which("helm")
    if helm is None:
        return
    result = subprocess.run(
        [helm, "template", "agentforge", str(CHART), "--set", "edgeGateway.enabled=true"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "kind: Gateway" in result.stdout
    assert "kind: HTTPRoute" in result.stdout
    assert "gatewayClassName: eg" in result.stdout
