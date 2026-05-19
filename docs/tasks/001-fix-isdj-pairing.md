# 任务 001：修正 ISDJ 配对

## 状态：已完成（部分）

## 执行结果

- config.py 的 ISDJ 已经正确配对 FastSlowTimeProcessor（无需修改）
- validate_algorithms.py 和 run_correctness_tests.py 的 ISDJ 配对已修正

## 测试结果

- ISDJ vs FastSlowTimeProcessor：SINR 改善 -1.97 dB（FAIL）
- 配对修正后仍然恶化，说明 **FastSlowTimeProcessor 的算法实现对 ISDJ 不够有效**
- 需要在任务 003 中改进算法本身

## 修改的文件

- `validate_algorithms.py` — ISDJ 从 Frequency_agile 改为 FastSlowTimeProcessor
- `run_correctness_tests.py` — ISDJ 从 Frequency_agile 的 jammers 移到 FastSlowTimeProcessor
