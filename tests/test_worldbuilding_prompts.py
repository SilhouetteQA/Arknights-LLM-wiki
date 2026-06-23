from arknights_wiki.extraction.worldbuilding_prompts import (
    build_book_system_prompt,
    build_book_user_prompt,
    build_video_system_prompt,
    build_video_user_prompt,
    build_seed_context,
)


class TestBookPrompts:
    def test_book_system_prompt_contains_categories(self):
        """system prompt 包含六子类说明"""
        prompt = build_book_system_prompt()
        assert "自然现象/物质" in prompt
        assert "种族/血脈" in prompt
        assert "超自然存在" in prompt

    def test_book_system_prompt_no_json_block(self):
        """system prompt 不含 markdown code block"""
        prompt = build_book_system_prompt()
        assert "```json" not in prompt

    def test_book_user_prompt_includes_chapter_content(self):
        """user prompt 包含章节文本"""
        prompt = build_book_user_prompt(
            chapter_title="第一章：源石",
            chapter_text="## 第 3 页\n源石是泰拉世界的基础..."
        )
        assert "第一章：源石" in prompt
        assert "源石是泰拉世界的基础" in prompt

    def test_book_user_prompt_includes_output_schema(self):
        """user prompt 包含输出格式说明"""
        prompt = build_book_user_prompt("test", "content")
        assert "concepts" in prompt.lower()


class TestVideoPrompts:
    def test_video_system_prompt_mentions_enrichment(self):
        """视频 system prompt 强调丰富已有实体"""
        prompt = build_video_system_prompt()
        assert "丰富" in prompt or "补充" in prompt or "已有" in prompt

    def test_video_user_prompt_without_seed(self):
        """无种子库时的 user prompt"""
        prompt = build_video_user_prompt("video content", seed_context="")
        assert "video content" in prompt

    def test_video_user_prompt_with_seed(self):
        """有种子库时的 user prompt 包含已知实体列表"""
        seed = build_seed_context({"concepts": [], "factions": [], "locations": []})
        prompt = build_video_user_prompt("video content", seed_context=seed)
        assert len(prompt) > 0

    def test_video_prompt_mentions_publish_date_context(self):
        """视频提示词包含发布时间上下文说明"""
        prompt = build_video_system_prompt()
        assert "发布时间" in prompt


class TestSeedContext:
    def test_build_seed_context_empty_db(self):
        """空种子库产出简洁提示"""
        ctx = build_seed_context({"concepts": [], "factions": [], "locations": []})
        assert isinstance(ctx, str)

    def test_build_seed_context_with_entities(self):
        """有实体时列出名称和分类"""
        seed_db = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质", "definition": "核心能源"},
                {"name": "萨卡兹", "category": "种族/血脈", "definition": "古老种族"},
            ],
            "factions": [
                {"name": "维多利亚", "category": "nation", "definition": "帝国"},
            ],
            "locations": [],
        }
        ctx = build_seed_context(seed_db)
        assert "源石" in ctx
        assert "萨卡兹" in ctx
        assert "维多利亚" in ctx
        assert "自然现象/物质" in ctx
