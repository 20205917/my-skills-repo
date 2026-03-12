---
name: personal-workstyle
description: 在每次新对话开始时触发，用于加载并执行个人长期工作规则，保障跨项目/跨会话/跨设备的一致偏好。覆盖语言、流程、输出格式与 Git 提交约束；中文要求不仅适用于文档说明，也适用于 commit message 与 commit body。支持规则的罗列、新增、删减、加载。
---

# Personal Workstyle Skill（个人工作风格）

这个 skill 用于统一并执行用户的长期偏好与流程规则。

## 何时使用
- 每次新对话开始时，优先加载并应用已生效规则。
- 用户要求应用个人偏好（语言、流程、输出格式、Git 提交规范）。
- 用户要求罗列/新增/删减/更新长期规则。

## 必须执行的流程
1. 每次新对话开始先加载 `rules/active.md`。
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
- 默认使用中文，适用于文档说明与 Git 提交（commit message / commit body）。
- 迭代总结：Done / Decision / Next。

## 文件说明
- `rules/active.md`：当前生效规则
- `rules/pending.md`：待确认规则
- `rules/history.md`：规则变更历史
- `templates/plan-template.md`：计划草案模板
