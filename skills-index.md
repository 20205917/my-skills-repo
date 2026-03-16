# Skills Index

- `data-generator`
  - 用途：根据 DDL 生成满足约束的 SQL/JSON 测试数据
  - 入口：`skills/data-generator/scripts/generate_test_data.py`

- `bug-fix-loop`
  - 用途：把报错排查做到“诊断-修复-验证-提交-部署/回滚”的可执行闭环
  - 入口：`skills/bug-fix-loop/SKILL.md`

- `dev2release`
  - 用途：在开发完成后补齐打包、文档、Changelog 与 GitHub Release 的发布准备闭环
  - 入口：`skills/dev2release/SKILL.md`

- `agents-bootstrap`
  - 用途：初始化全局级与项目级 AGENTS.md，生成可维护的精简执行型模板并给出加载优先级验证步骤
  - 入口：`skills/agents-bootstrap/scripts/init_agents_md.py`

- `xlsx2json`
  - 用途：将 XLSX 每行数据转换为 JSON，支持列名映射与 enum 值映射
  - 入口：`skills/xlsx2json/scripts/xlsx_to_json.py`
