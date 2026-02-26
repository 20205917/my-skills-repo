---
name: personal-workstyle
description: 当用户希望在跨项目/跨会话/跨设备中保持个人偏好与工作流程一致时使用。支持规则的罗列、新增、删减、加载；并要求大计划先确认再固化。
---

# Personal Workstyle Skill（个人工作风格）

这个 skill 用于统一并执行用户的长期偏好与流程规则。

## 何时使用
- 用户要求应用个人偏好（语言、流程、输出格式）。
- 用户要求罗列/新增/删减/更新长期规则。
- 用户要求“大计划先确认，再固化”。

## 必须执行的流程
1. 先加载 `rules/active.md`。
2. 按已生效规则执行当前任务。
3. 当用户要求修改规则时：
   - 先写入 `rules/pending.md`（待确认）。
   - 用户明确确认后，再合并到 `rules/active.md`。
   - 所有变化追加到 `rules/history.md`。
4. 对较大实现计划：必须先出 Draft，等待用户明确确认后，才允许写入项目正式文档。

## 规则操作命令
使用 `scripts/rules.py`：
- 罗列生效规则：`python3 scripts/rules.py list`
- 新增待确认规则：`python3 scripts/rules.py add "<规则内容>"`
- 待确认转生效：`python3 scripts/rules.py promote <id>`
- 删除生效规则：`python3 scripts/rules.py remove <id>`
- 加载并显示当前规则：`python3 scripts/rules.py load`

## 默认内置行为
- 默认使用中文。
- 大计划：先 Draft，再确认，再固化。
- 迭代总结：Done / Decision / Next。

## 文件说明
- `rules/active.md`：当前生效规则
- `rules/pending.md`：待确认规则
- `rules/history.md`：规则变更历史
- `templates/plan-template.md`：计划草案模板
