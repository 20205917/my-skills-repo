# My Skills Repo

这是一个面向使用者的技能集合仓库。你可以在对话中直接调用技能，完成排障、数据生成、发布准备等任务。

## 如何使用

1. 在对话里描述你的目标和上下文（报错、DDL、发布目标、规则偏好等）。
2. 明确指定技能名（例如：`$bug-fix-loop`、`$data-generator`）。
3. 按技能要求补充输入信息，等待执行结果与下一步建议。

## 可用技能

- `bug-fix-loop`
  - 用途：把报错排查做到“诊断-修复-验证-提交-部署/回滚”的可执行闭环。
  - 示例：`使用 $bug-fix-loop 修复这个 CI 失败，给我最小改动方案。`
- `data-generator`
  - 用途：根据 MySQL/PostgreSQL DDL 生成满足约束的 SQL/JSON 测试数据。
  - 示例：`使用 $data-generator 根据 schema.sql 生成 1000 条测试数据。`
- `personal-workstyle`
  - 用途：管理个人长期规则，并在每次新对话开始时加载执行。
  - 示例：`使用 $personal-workstyle 把“提交前必须检查 git status”加入规则。`
- `dev2release`
  - 用途：在开发完成后补齐打包、文档、Changelog 与 GitHub Release。
  - 示例：`使用 $dev2release 对当前项目做发布前准备并生成发布说明。`

更多技能索引见 [skills-index.md](skills-index.md)。

## 使用建议

- 报错排查类任务优先给日志、命令输出、复现步骤。
- 数据生成类任务优先提供 DDL 和目标行数。
- 发布类任务优先提供目标版本号、分支、发布平台。
- 规则治理类任务优先说明“要新增/删除/生效”的具体规则。

## 开发与维护文档

原 README 中面向开发者的内容（目录结构、脚本命令、测试、维护约定）已迁移到：

- [AGENTS.md](AGENTS.md)
