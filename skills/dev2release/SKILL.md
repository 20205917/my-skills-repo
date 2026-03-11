---
name: dev2release
description: 阶段开发完成后，对项目进行可用化与发布准备的执行型技能。用于用户要求完善项目打包流程、编写或更新使用说明文档、编写或更新 Changelog、执行 GitHub Release（含版本号与 Tag）时。默认执行最小发布闸门：打包成功、核心测试通过、工作区干净、Changelog 已更新，并在失败场景提供可执行回滚方案。
---

# Dev2Release

在本技能中，始终以“最小改动完成可发布闭环”为目标。优先复用现有流程，仅在缺失时补齐。

## 执行原则

1. 先探测现状，再决定是否改动。
2. 优先复用已有打包和发布入口，避免重复造轮子。
3. 默认执行最小发布闸门，不跳过核心校验。
4. 无法唯一判断时，最多补充 3 个必要问题后继续执行。
5. 发布动作默认面向 GitHub Release；若 `gh` 不可用则降级为 Tag + 手工发布指引。

## 阶段 1：发布前探测

按以下顺序探测，不先改文件：

```bash
pwd
rg --files | head -n 200
git status --short
git branch --show-current
git remote -v
git describe --tags --abbrev=0 2>/dev/null || echo "NO_TAG"
```

确认并输出：

1. 当前分支、远程仓库与工作区是否干净。
2. 上一个版本标识（Tag 或首次发布）。
3. 技术栈命中结果（Node/Java/Python）。
4. 是否存在可复用打包入口。

## 阶段 2：补齐打包流程

先读取 [references/release-command-matrix.md](references/release-command-matrix.md) 选择命令模板。

执行策略：

1. 若仓库已有稳定打包入口（Makefile、CI 脚本、构建脚本），直接复用并验证。
2. 若缺失打包入口，按技术栈补最小可执行入口（优先 `scripts/package.sh` 或等价 `make package`）。
3. 仅补充必要文件，不做无关重构。

最小发布闸门中“打包成功”必须满足：

- 目标产物可生成，且命令可重复执行。
- 命令写入 README 发布段落或现有构建文档。

## 阶段 3：更新使用说明文档

默认更新 README 的发布相关段落，至少包含：

1. 打包前置条件。
2. 打包命令与产物位置。
3. 发布步骤（版本、Tag、Release）。
4. 回滚入口或回退命令说明。

要求：

- 保持与现有文档风格一致。
- 示例命令必须可复制。
- 文档与实际执行命令一致。

## 阶段 4：更新 Changelog

默认采用 Conventional Commits 汇总，从上一个 Tag 到 `HEAD` 生成当前版本条目。

示例：

```bash
python3 skills/dev2release/scripts/conventional_changelog.py \
  --from-ref "$LAST_TAG" \
  --to-ref HEAD \
  --version "$VERSION" \
  --date "$TODAY" \
  --changelog CHANGELOG.md \
  --write
```

需要自动判断版本级别时：

```bash
python3 skills/dev2release/scripts/conventional_changelog.py \
  --from-ref "$LAST_TAG" \
  --to-ref HEAD \
  --infer-bump
```

## 阶段 5：版本、Tag 与 GitHub Release

默认流程：

```bash
gh auth status
git status --short

# 生成 release notes 预览
python3 skills/dev2release/scripts/conventional_changelog.py \
  --from-ref "$LAST_TAG" \
  --to-ref HEAD \
  --version "$VERSION" \
  --date "$TODAY" > RELEASE_NOTES.md

# 提交发布相关变更
git add README.md CHANGELOG.md
git commit -m "chore(release): v$VERSION"

# 打 tag 并推送
git tag -a "v$VERSION" -m "release v$VERSION"
git push origin HEAD
git push origin "v$VERSION"

# 创建 GitHub Release
gh release create "v$VERSION" \
  --title "v$VERSION" \
  --notes-file RELEASE_NOTES.md
```

若 `gh` 不可用：

1. 继续完成 `git tag` 与 `git push`。
2. 输出 GitHub 网页端手工创建 Release 的参数（tag、title、notes）。

## 阶段 6：发布后验证与回滚

发布后验证：

```bash
gh release view "v$VERSION"
git ls-remote --tags origin | rg "v$VERSION"
```

失败回滚模板：

```bash
# 删除 GitHub Release（如已创建）
gh release delete "v$VERSION" --yes

# 删除远端与本地 tag
git push --delete origin "v$VERSION"
git tag -d "v$VERSION"

# 必要时回退发布提交
git revert <release-commit-sha>
```

## 固定输出结构

每次执行该技能时，输出必须包含以下 6 个区块：

1. 发布准备摘要
2. 打包流程变更
3. 文档变更
4. Changelog 条目
5. Release 执行命令
6. 回滚命令

每个区块都必须给出可复制命令或明确文件改动点。
