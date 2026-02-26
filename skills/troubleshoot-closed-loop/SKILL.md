---
name: troubleshoot-closed-loop
description: 面向真实工程故障排查与修复闭环的执行型技能。用于输入是报错截图、终端输出、监控图、网页错误页、CI 失败截图、日志/异常栈/配置片段，或用户明确要求“修复编译、修复运行错误、修复测试、修复 CI、修复网络/代理/Git 鉴权、可选部署”等动作时。执行从信息提取、复杂度评估、最小复现、根因定位、最小改动修复、测试验证、Git 提交到可选部署与回滚的全流程。
---

# Troubleshoot Closed Loop

在本技能中，始终先完成“问题闭环”，再扩展优化。默认最小改动，避免无关重构。

## 占位符

在命令和模板中使用以下可替换占位符：

- `<REPO_ROOT>`：仓库根目录
- `<BRANCH>`：工作分支
- `<BUILD_TOOL>`：`maven` 或 `gradle`
- `<DEPLOY_ENV>`：`dev` / `test` / `prod`

## 输入处理规则

1. 若输入是图片：
   - 先文字化提取要点：错误码、异常类型、关键堆栈行、文件路径、模块名、时间、执行命令、CI job 名。
   - 标注不确定项，避免把不可读区域当事实。
2. 若输入是文本：
   - 抽取同样的结构化要点，并标注缺失字段。
3. 若用户指定“需要完成的动作”：
   - 以该动作作为主目标组织后续全部输出和执行顺序。

## 仓库探测命令清单（信息不足时优先执行，不先提问）

```bash
cd <REPO_ROOT>

# 1) 基础结构
pwd
ls -la
rg --files | head -n 200

# 2) 构建工具与测试框架探测
test -f pom.xml && echo "BUILD_TOOL=maven"
test -f build.gradle -o -f build.gradle.kts && echo "BUILD_TOOL=gradle"
rg -n "spring-boot|springframework.boot|javafx|picocli|junit|testng" pom.xml build.gradle* settings.gradle* gradle.properties

# 3) CI/部署入口探测（按优先级）
find . -maxdepth 3 -type f \( -name "deploy.sh" -o -name "release.sh" -o -name "deploy*.sh" \)
test -f Makefile && rg -n "^deploy:|^release:" Makefile
find . -maxdepth 4 -type f \( -name "docker-compose.yml" -o -name "docker-compose.yaml" -o -name "Chart.yaml" \)
find . -maxdepth 4 -type f \( -path "./.github/workflows/*" -o -name ".gitlab-ci.yml" -o -name "Jenkinsfile" \)
rg -n "deploy|release|上线|发布|rollback|回滚" README* docs/*

# 4) 故障证据定位
rg -n "ERROR|Exception|FAILED|Caused by|timeout|auth|permission|denied|refused|proxy|SSL" . --glob "!**/node_modules/**" --glob "!**/.git/**"
```

## 复杂度评估（0-10）与模式选择

先评分，再决定 `One-pass` 或 `Two-phase`。

### 评分维度（7 项，每项 0-2 分）

1. 复现明确性：稳定复现=0；偶发=1；不可复现/未知=2  
2. 系统跨度：单模块=0；跨模块=1；跨服务/分布式=2  
3. 风险与回滚：无数据/低风险=0；中风险=1；数据迁移/高风险/难回滚=2  
4. 安全鉴权：不涉及=0；普通权限=1；凭据/鉴权/安全策略=2  
5. 环境差异：单环境一致=0；dev/test 差异=1；prod/容器/CI 差异复杂=2  
6. 证据完整度：日志栈完整=0；部分缺失=1；仅模糊现象或截图=2  
7. 变更规模：预计 1-2 文件=0；3-5 文件=1；>5 文件或需新脚本/配置链路=2

`score_10 = round((sum / 14) * 10, 1)`

### 证据充分度闸门（evidence gate）

满足以下 4 条记为 `gate=pass`，否则 `gate=fail`：

1. 有可执行复现命令或明确触发步骤。
2. 有可定位模块的错误证据（堆栈/日志/CI 关键片段）。
3. 根因候选可落到具体文件/函数/配置点。
4. 有可执行验证命令与通过标准。

### 模式映射（含闸门与例外）

- `0.0 - 4.0` 且 `gate=pass`：`One-pass`
- `0.0 - 4.0` 且 `gate=fail`：`Two-phase`
- `4.1 - 6.5`：默认 `Two-phase`；若 `gate=pass` 且根因置信度高，可 `One-pass`
- `6.6 - 10.0`：默认 `Two-phase`

在以下条件同时满足时，允许“高置信直修”例外（即使分数偏高也可 `One-pass`）：

1. 复现稳定且根因锚点明确。
2. 预计改动不超过 2 个文件。
3. 已给出回滚方式。
4. 用户目标是“尽快恢复”。

## Two-phase 硬规则

1. 第一阶段默认只做诊断/复现/定位，不改代码。
2. 第一阶段最多请求 3 项回传信息，并提供可复制命令。
3. 允许 1 次补充提问，每次最多 3 项，仅在首批信息不足以定位时使用。
4. 信息不足但可探测时，先给探测命令，不先提问。
5. 第二阶段在拿到回传后，完成修复、验证、提交（和可选部署）闭环。

## 执行流程（统一主线）

1. 解析输入并抽取证据。
2. 执行复杂度评估，选 `One-pass` 或 `Two-phase`。
3. 复现并定位根因（优先最小复现路径）。
4. 设计最小改动方案（文件/函数/配置粒度）。
5. 执行修复并验证（单测/集成/构建/运行/CI 对齐）。
6. 生成 Git 方案（分支、提交信息、拆分策略）。
7. 可选部署（按部署规则）并给回滚策略。

## 部署规则（按需触发）

仅在以下场景触发部署流程：

1. 用户明确要求部署/发布/上线。
2. 当前任务目标包含部署验证。
3. 修复已可发布且用户同意进入部署阶段。

若未触发部署流程，不生成部署脚本，仅给“部署准备度与缺口清单”。

### 1) 先搜索现有部署入口（固定优先级）

1. `scripts/deploy*.sh`、`deploy.sh`、`release.sh`
2. `Makefile` 的 `deploy/release` target
3. `docker-compose.yml` / Helm chart / K8s manifests
4. CI：`.github/workflows/*`、`.gitlab-ci.yml`、`Jenkinsfile`
5. `README` 的 deploy/release/上线段落

### 2) 若找到入口

输出以下内容：

- 脚本或入口路径
- 用法和参数
- 执行命令（尽量含预检）
- 部署后检查命令

### 3) 若未找到入口（且已触发部署流程）

先询问最少必要信息（一次最多 3 项），例如：

1. `<DEPLOY_ENV>` 与目标主机/平台类型
2. 制品类型（jar/docker image）与拉取方式
3. 启停与健康检查方式

然后：

- 生成最小 `scripts/deploy.sh` 草案或 `Makefile deploy` 草案
- 生成 README 部署段落草案
- 用户补充后再给最终可运行命令

### 4) 必须给回滚方式

至少给出一个可执行回滚命令或策略（版本回退、镜像回滚、配置回滚）。

## Git 提交规范（在修复落地阶段遵循）

仅当本轮输出包含实际代码/配置改动时，强制给出 Git 提交方案。纯诊断回合不强制提交。

1. 分支命名建议：
   - `fix/<keyword>`
   - `hotfix/<keyword>`
   - `chore/<keyword>`
2. 提交信息必须贴切、可追溯，并带 scope（可推断时）：
   - `fix(auth): handle proxy credential refresh failure`
3. commit body 必须包含四段：
   - `Root cause`
   - `Changes`
   - `Verification`
   - `Impact`
4. 默认一个问题一个 commit。
5. 若包含机械格式化或重构，必须拆分 commit 并解释拆分原因。
6. 严禁提交信息包含敏感信息（token/密码/私钥/敏感内网地址）。

## 安全与工程约束（必须遵循）

- 不索要、不输出任何密钥、token、密码、私钥。
- 日志若含敏感信息，提醒先打码再贴。
- 禁止建议破坏性命令（如 `rm -rf`、删库、清空目录）。
- 若确需高风险动作，先解释风险，并给替代方案与回滚方案。
- 默认最小改动；避免无意义格式化和不必要依赖。
- 无法代执行命令时，也必须给“可复制命令 + 预期输出/判定标准”。
- Java 项目优先识别 `Maven/Gradle`、`JUnit`、`Spring Boot/JavaFX/CLI` 并选对应命令。
- 默认离线排查；若问题依赖远端状态（如 CI/依赖仓库/镜像仓库），先请求用户授权后再进入受控联网诊断，并声明命令范围。

## 固定输出结构（分层必选）

### 基础必选（所有回复都要有）

A. 问题摘要（现象/影响/环境/触发）  
B. 复杂度评估（评分 + 依据 + 模式选择）  
D. 计划（复现 -> 定位 -> 修复 -> 验证 -> 提交 -> 部署）  
E. 执行步骤（可复制命令，按顺序，含预期结果/判定标准）

### 条件必选（按场景附加）

- C. 根因候选：有多种可能性时必须给（2-4 个按概率排序）。
- F/G/H：当输出包含代码或配置改动时必须给。
- I：仅在部署流程触发时必须给。
- J：涉及风险、兼容性或回滚时必须给（建议默认给简版）。

### One-pass 输出（闭环版）

通常包含：`A/B/C/D/E/F/G/H`。  
部署触发时追加 `I/J`，未触发部署时可省略 `I`。

### Two-phase 第一次输出（诊断版）

默认输出：`A/B/C/D/E`。  
明确“本阶段默认不改代码”。  
在 `E` 中给获取关键证据的命令。  
首批最多要求回传 3 项信息。

### Two-phase 第二次输出（闭环版）

用户回传后，补齐并输出：`F/G/H`，按需追加 `I/J`，完成闭环。

## 命令模板（按构建工具自动选择）

```bash
cd <REPO_ROOT>
git checkout -b <BRANCH>

# Maven
./mvnw -q -DskipTests compile
./mvnw -q test

# Gradle
./gradlew classes
./gradlew test
```

若命令失败，输出：

1. 失败点（哪条命令、哪类错误）
2. 下一步最小诊断命令
3. 成功/失败判定标准
