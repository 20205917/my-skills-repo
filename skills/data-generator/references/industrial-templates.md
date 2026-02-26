# 工业模板

## 常见实体

本技能优先支持以下工业实体：

- `lines`（产线）
- `stations`（工位）
- `devices`（设备）
- `sensors`（传感器）
- `sampling_points`（采集点）
- `measurements`（采样数据）
- `alarms`（告警）
- `work_orders`（工单）
- `maintenance_records`（维护记录）
- `spare_parts`（备件）
- `inventory`（库存）
- `shifts`（班次）

## 推荐关系骨架

- `lines 1:N devices`
- `devices 1:N sensors`
- `sensors 1:N measurements`
- `measurements -> alarms`（阈值或尖峰触发）
- `alarms -> work_orders`（按比例转工单）
- `work_orders -> maintenance_records`
- `spare_parts -> inventory`

如果用户实际表名不同，使用 FK 覆盖映射。

## 时间事件链

字段具备时，优先采用以下顺序：

1. 设备投产/创建
2. 采样产生
3. 告警产生
4. 工单创建
5. 维护开始/结束
6. 工单关闭

关联记录尽量保持时间单调递增。

## 默认工业数值范围

- 温度：`25 ~ 95`
- 压力：`0.8 ~ 8.0`
- 振动：`0.1 ~ 12.0`
- 电流：`1 ~ 60`
- 电压：`180 ~ 450`
- 转速：`300 ~ 4000`
- 湿度：`20 ~ 95`

可注入少量尖峰，模拟告警触发。

## 比例参数建议

- `--line-devices`：每条产线设备数（默认 8）
- `--device-sensors`：每台设备传感器数（默认 4）
- `--alarm-work-order-ratio`：告警转工单比例（默认 0.35）

这些是软约束，优先保证关系完整性。

## 状态流转建议

- `alarm_status`：`NEW -> ACKED -> IN_PROGRESS -> RESOLVED -> CLOSED`
- `work_order_status`：`CREATED -> ASSIGNED -> IN_PROGRESS -> DONE -> CLOSED`
- `qc_result`：`PASS/FAIL/REWORK`

若用户未提供完整状态机，采用保守随机策略并保证时间一致性。
