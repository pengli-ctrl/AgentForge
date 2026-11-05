"""校验新增集成测试是否接入 GitHub Actions。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/integration.yml").read_text(encoding="utf-8")
required = ["compose-integration", "gateway-kind", "security-integration", "observability-integration", "docker compose -f deploy/local/docker-compose.integration.yml", "helm/kind-action", "pytest tests/integration"]
missing = [item for item in required if item not in workflow]
if missing:
    raise SystemExit("integration gate missing: " + ", ".join(missing))
print("integration gate passed")
