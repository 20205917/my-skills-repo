# Release Command Matrix

## 1. 技术栈探测规则

按以下顺序判断：

1. Node：存在 `package.json`。
2. Java Maven：存在 `pom.xml`。
3. Java Gradle：存在 `build.gradle` 或 `build.gradle.kts`。
4. Python：存在 `pyproject.toml` 或 `setup.py`。

若命中多个栈：

1. 优先用户显式要求的目标模块。
2. 若未指定，优先仓库主入口模块（根目录构建文件）。
3. 仍不明确时，仅补充最多 3 个必要问题后继续。

## 2. 打包命令模板

### Node

- 依赖安装：
  - `pnpm-lock.yaml` 存在：`pnpm install --frozen-lockfile`
  - `yarn.lock` 存在：`yarn install --frozen-lockfile`
  - 默认：`npm ci`
- 打包命令：
  - 存在 `scripts.build`：`npm run build` 或对应包管理器命令
  - 不存在 `scripts.build`：补最小 `scripts/package.sh`，并在 README 说明用途

### Java Maven

- 优先 `./mvnw`：`./mvnw -B clean package`
- 否则：`mvn -B clean package`

### Java Gradle

- 优先 `./gradlew`：`./gradlew clean build`
- 否则：`gradle clean build`

### Python

- `pyproject.toml`：`python3 -m build`
- `setup.py`：`python3 setup.py sdist bdist_wheel`

## 3. 核心测试模板

最小闸门中的“核心测试通过”默认命令：

- Node：`npm test -- --watch=false` 或仓库既有测试命令
- Maven：`mvn -B test`
- Gradle：`gradle test` 或 `./gradlew test`
- Python：`python3 -m pytest` 或仓库既有测试命令

若仓库没有测试框架，需在输出中明确记录“测试缺口”并请求用户确认。

## 4. 发布前检查模板

```bash
git status --short
git fetch --tags
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
```

检查项：

1. 工作区干净。
2. Changelog 已包含目标版本。
3. 打包命令成功。
4. 核心测试通过。
