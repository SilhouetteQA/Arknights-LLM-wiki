"""T3: 材料清单校验测试"""
import json
from pathlib import Path

MATERIALS = Path("benchmarks/arknights_bench/materials")
ANGLES = ["character", "event", "region", "organization", "combat_power", "worldview"]
MIN_COUNTS = {"character": 40, "event": 60, "region": 24, "organization": 24, "combat_power": 32, "worldview": 32}


def _load_all(angle: str) -> list[dict]:
    items = []
    for p in MATERIALS.glob(f"{angle}*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        items.extend(data.get("items", []))
    return items


class TestMaterials:
    def test_all_angles_present(self):
        files = {p.name for p in MATERIALS.glob("*.json")}
        for a in ANGLES:
            assert any(f.startswith(a) for f in files), f"缺角度 {a} 材料文件"

    def test_min_counts(self):
        for a in ANGLES:
            assert len(_load_all(a)) >= MIN_COUNTS[a], f"{a} 条数不足: {len(_load_all(a))}"

    def test_schema(self):
        for a in ANGLES:
            for it in _load_all(a):
                assert it["name"], f"{a} 缺 name"
                assert it["source_file"], f"{a} {it['name']} 缺 source_file"
                assert it["excerpt"], f"{a} {it['name']} 缺 excerpt"
                assert isinstance(it.get("meta"), dict), f"{a} {it['name']} 缺 meta"

    def test_source_files_exist(self):
        missing = []
        for a in ANGLES:
            for it in _load_all(a):
                p = Path(it["source_file"])
                if not p.exists():
                    missing.append(f"{a}/{it['name']}: {it['source_file']}")
        assert not missing, f"缺失源文件: {missing[:5]}"
