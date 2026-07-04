"""Pass 1 全量提取启动脚本"""
from arknights_wiki.extraction.orchestrator import run_all, generate_run_report, _estimate_cost
import traceback

print("=" * 50)
print("Pass 1 全量批量提取")
print("=" * 50)

results = run_all(resume=True)

# 保存报告
report = generate_run_report()
with open("output/pass1_run_report.md", "w", encoding="utf-8") as f:
    f.write(report)

print("\n报告已保存到 output/pass1_run_report.md")

# 检查失败
failed = [r for r in results if "_error" in r]
if failed:
    print(f"\n失败章节 ({len(failed)}):")
    for r in failed:
        print(f"  [{r.get('category')}] {r['chapter']}: {r['_error']}")
