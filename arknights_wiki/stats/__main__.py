"""统计系统 CLI 入口 — python -m arknights_wiki.stats"""
import argparse
import os
import sys


def main():
    # Windows 终端 GBK 编码兼容：强制 UTF-8 输出
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    parser = argparse.ArgumentParser(description='开发过程统计')
    parser.add_argument('--last', type=int, metavar='N',
                        help='显示最近 N 次快照')
    parser.add_argument('--diff', action='store_true',
                        help='对比最近两次快照')
    parser.add_argument('--jsonl', default=None,
                        help='JSONL 文件路径 (默认: output/stats.jsonl)')
    args = parser.parse_args()

    # 默认 JSONL 路径
    if args.jsonl is None:
        import pathlib
        pkg_dir = pathlib.Path(__file__).resolve().parent.parent.parent
        jsonl_path = str(pkg_dir / 'output' / 'stats.jsonl')
    else:
        jsonl_path = args.jsonl

    from arknights_wiki.stats.reporter import StatsReporter
    reporter = StatsReporter(jsonl_path)

    if args.diff:
        reporter.show_diff()
    elif args.last is not None:
        reporter.show_last(args.last)
    else:
        reporter.show_latest()


if __name__ == '__main__':
    main()
