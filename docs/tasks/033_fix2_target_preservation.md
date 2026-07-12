# Task 033-fix2：建立独立目标保真度评价分支

## 目标

在现有污染接收评价之外，增加 target-only 分支：将理想 target 单独输入算法，比较处理后目标响应与 clean target 响应，避免把残余 jammer/noise 当作算法目标损伤。

## 新指标

```text
target_only_response_change_db
    = 20log10(A(processed_clean_target) / A(clean_target))
```

保留污染 received 分支的旧参考响应，但字段改为 `processed_reference_response_vs_clean_db`，不参与推荐结论。

## 限制

只修改 evaluation、validation script、报告和结果；不修改 jammer、JSR、radar config、antijam、RL、reward、state 或 PPO；不使用 target_idx、jammer signal 或 jammer type 作为算法输入。

## 验收

- target-only API 存在；
- `evaluation_v3` 完成 3360 cases；
- 推荐规则使用 target-only response change；
- v2 结果保留不覆盖；
- 完成报告和独立提交 `phase1-033-fix2-target-preservation`。
