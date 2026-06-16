"""统计收集器 — 收集开发过程指标并写入 JSONL"""
import json as _json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone


class StatsCollector:
    pass
