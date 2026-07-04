# Pass 3 试跑问题修复方案

> **状态**: 已完成

> 基于 7 章试跑发现的 8 个问题，按根因分组，每项含具体修复代码。

---

## 问题清单

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| 1 | 组织 member_composition 填充率仅 18% | 高 | Phase 3 输出 schema 缺 member_composition 字段 |
| 2 | 新实体 story_events 标记"未知章节" | 中 | merge 代码未对新实体的 events 回填 source_chapter |
| 3 | 赤霄、虚假的天空、黄金时代 未提取 | 中 | prompt 对"核心设定揭示"敏感度不够 |
| 4 | 无胄盟/红松骑士团 concepts 和 factions 重复 | 中 | LLM 对同一实体在 concepts/factions 各创建一份 |
| 5 | 新增实体有定义无 story_events | 中 | LLM 输出新实体时 story_events 为空 |
| 6 | 耀骑士误提取为概念 | 低 | 角色称号未被 prompt 正确排除 |
| 7 | 少量"未直接出现"类空事件占位 | 低 | LLM 对未出现实体输出占位事件 |

---

## 修复 1: 组织 member_composition 填充

**文件**: `worldbuilding_prompts.py` — `_PHASE3_SYSTEM_PROMPT` + `_PHASE3_OUTPUT_SCHEMA`

**变更 1a**: system prompt 新增人物-组织归属任务

```diff
  _PHASE3_SYSTEM_PROMPT = """...
  ## 任务
  ...

+ ### 3. 人物-组织归属（仅在 entity_type=faction 时）
+ 对于剧情中出现的阵营（nation/organization），提取其出场成员信息:
+ - 成员名: 完整角色名（注意区分代号/真名/异格）
+ - 角色: 在该组织中的职位或身份
+ - 本章表现: 该角色在本章中的关键行动（1-2句话）
+
+ 注意: 只记录在本章剧情中实际出场或通过对话明确提及的成员，不编造。
+
  ## 重要规则
  ...
```

**变更 1b**: 输出 schema 新增 members 字段

```diff
  _PHASE3_OUTPUT_SCHEMA = """{
    "entity_mentions": [
      {
        "entity_name": "已知实体名",
        "entity_type": "concept/faction/location",
        "story_events": [...],
+       "members": [
+         {
+           "name": "角色名",
+           "role": "职位/身份",
+           "chapter_role": "本章中的表现"
+         }
+       ]
      }
    ],
    ...
```

**变更 1c**: 合并逻辑新增 members 字段处理

在 `_merge_phase3_result` 中，`entity_mentions` 合并循环内新增:

```python
# 合并 members（去重: 同名+同role视为重复）
existing_members = merged[etype_plural][idx].get("member_composition", [])
new_members = mention.get("members", [])
existing_keys = {(m.get("name",""), m.get("role","")) for m in existing_members}
for m in new_members:
    key = (m.get("name",""), m.get("role",""))
    if key not in existing_keys:
        existing_members.append(m)
        existing_keys.add(key)
merged[etype_plural][idx]["member_composition"] = existing_members
```

---

## 修复 2: 新实体 story_events 无 source_chapter

**文件**: `worldbuilding_orchestrator.py` — `_merge_phase3_result`

**Bug**: 第 377 行新实体直接 append，其自带 story_events 没有 source_chapter 回填。

**修复**:

```diff
          else:
              entity["story_events"] = entity.get("story_events", [])
+             for ev in entity["story_events"]:
+                 ev["source_chapter"] = chapter_name
              merged[etype].append(entity)
              entity_index.setdefault(etype, {})[name] = len(merged[etype]) - 1
```

--- 同时修复: 新实体首次出现时无 story_events 应在合并时创造一条:

```diff
          else:
              entity["story_events"] = entity.get("story_events", [])
+             if not entity["story_events"]:
+                 entity["story_events"] = [{
+                     "name": f"{entity['name']}首次出现",
+                     "description": f"在{chapter_name}剧情中首次出现",
+                     "significance": "major",
+                     "source_chapter": chapter_name,
+                 }]
              for ev in entity["story_events"]:
                  ev["source_chapter"] = chapter_name
```

---

## 修复 3: 核心设定揭示 — 三级事件体系 + 原文引用解读

**文件**: `worldbuilding_prompts.py` — `_PHASE3_SYSTEM_PROMPT` + `_PHASE3_OUTPUT_SCHEMA`

**设计**: 事件重要程度从 major/minor 扩展为三级，新增 `revelation` 最高级:

```
revelation (核心揭示) — 对实体的本质/起源/真相进行颠覆性或深层揭示
  ├─ 判定: 含「不是/其实是/本质是/原来是/真相是/假的/伪造的」等揭示性表述
  ├─ 描述: 80-150字，必须包含:
  │   (a) 谁在什么情境下揭示/发现了什么
  │   (b) 直接引用原文关键句（用「」标注，注明说话者）
  │   (c) 这个揭示对理解该实体意味着什么
  ├─ quote: 原文关键句（必填）
  └─ implication: 揭示的意义（必填，20-50字）

major (重要事件) — 实体是事件核心但非揭示性，30-80字

minor (背景提及) — 实体作为背景或间接提及，20-50字
```

**Wiki 渲染效果**: revelation 事件以 blockquote 突出显示:
```
> **「核心揭示」克里斯滕发现天空是假的**
>
> 克里斯滕在万星园突破星荚后对塞雷娅揭示了真相...
>
> 原文: 克里斯滕:「外面不是星空，是假的」
>
> **意味着:** 星荚不是物理屏障，而是被制造出来的伪装图层
```

---

## 修复 4: 实体跨层重复（concepts/factions 同名）

**文件**: `worldbuilding_orchestrator.py` — `_merge_phase3_result`

**策略**: 合并后检测 concepts 和 factions 中的同名实体，faction 优先保留。

```python
def _dedup_cross_type(seed_db: dict) -> dict:
    """如果同名实体同时在 concepts 和 factions 中，保留 factions 版本"""
    faction_names = {f["name"] for f in seed_db.get("factions", [])}
    removed = []
    seed_db["concepts"] = [
        c for c in seed_db.get("concepts", [])
        if c["name"] not in faction_names or removed.append(c["name"])
    ]
    if removed:
        print(f"  跨层去重: {removed} (concepts→删除, 保留factions)")
    return seed_db
```

在 `run_phase3_trial` 末尾、`save_seed_db` 之前调用。

---

## 修复 5+6+7: Prompt 微调（一次性处理）

**文件**: `worldbuilding_prompts.py` — `_PHASE3_SYSTEM_PROMPT`

```diff
- - 角色名（如阿米娅、凯尔希）不是世界观实体，不要提取
+ - 角色名、角色称号（如阿米娅、凯尔希、博士、耀骑士、临光）不是世界观实体，不要提取
+ - 但如果该称号同时是一个制度/职位（如「魔王」「天师」「雪祀」），则作为概念提取
  ...
+ - 不要输出「未直接出现」「剧情中未提及」等空事件占位。实体未出现就不输出
```

---

## 缺失实体补充（数据层一次性修复）

以下实体需手动补入种子库:

| 实体名 | 类型 | 分类 | 来源章节 |
|--------|------|------|----------|
| 赤霄 | concept | 技术/技艺体系 | 怒号光明 |
| 虚假的天空 | concept | 特殊地域/异域 | 孤星 |
| 伊比利亚黄金时代 | concept | 社会制度/文化 | 愚人号 |

删除:
- `concepts/无胄盟.md`（保留 `factions/无胄盟.md`）
- `concepts/红松骑士团.md`（保留 `factions/红松骑士团.md`）
- `concepts/耀骑士.md`（角色称号，非世界观实体）

---

## 实施顺序

| 步骤 | 内容 | 影响范围 |
|------|------|----------|
| 1 | 修复 2（source_chapter bug） | `worldbuilding_orchestrator.py` 5行 |
| 2 | 修复 1a/1b/5/6/7（prompt 综合升级） | `worldbuilding_prompts.py` ~30行 |
| 3 | 修复 1c（members 合并逻辑） | `worldbuilding_orchestrator.py` 8行 |
| 4 | 修复 4（跨层去重） | `worldbuilding_orchestrator.py` 12行 |
| 5 | 修复 3（揭示敏感度） | `worldbuilding_prompts.py` 4行 |
| 6 | 数据层: 删除重复实体 + 补充缺失实体 | `v3_seed_db_v3.json` 手动编辑 |
| 7 | 重新试跑 7 章验证 | 全 Pipeline |
