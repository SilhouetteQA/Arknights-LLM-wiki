#!/bin/bash
set -e
echo "[1/2] 从本地 Linux wheel 安装 deepeval..."
pip install --no-index --find-links /wheelhouse deepeval 2>&1 | tail -4
echo "[2/2] 验证导入..."
python -c "import deepeval; print('DEEPEVAL_OK', deepeval.__version__)"
echo "SETUP_DONE"
