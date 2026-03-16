# AGENTS 开发指南（{{PROJECT_NAME}}）

本文件是项目级 AGENTS 规则，优先约束当前仓库的开发与维护行为。

## 项目基础信息

- 项目类型：{{PROJECT_TYPE}}
- 核心技术栈：{{TECH_STACK}}
- 项目用途：{{PROJECT_PURPOSE}}
- 核心约束：
{{CORE_CONSTRAINTS}}

## 环境搭建与开发流程

{{DEV_WORKFLOW}}

## 测试规范

{{TEST_SPEC}}

## 约定规则

### 必须做

{{MUST_RULES}}

### 先询问

{{ASK_FIRST_RULES}}

### 绝对禁止

{{FORBIDDEN_RULES}}

## 项目级与子目录级修改规则

- 项目通用规则统一维护在仓库根目录 `AGENTS.md`。
- 仅当某子目录存在稳定且长期生效的差异规则时，才在该子目录新增 `AGENTS.md` 或 `AGENTS.override.md`。
- 子目录规则只覆盖该目录及其后代目录，不应重复项目级已有通用规则。
- 修改子目录规则时，先说明与项目级规则的差异点与影响范围，再执行变更。
- 若子目录规则与项目级规则冲突，以更近目录规则为准，并在变更说明中记录冲突处理结论。
