"""
冒烟测试 - 覆盖核心模块的关键行为（unittest，零新依赖）

运行: python -m unittest discover -s tests -v
"""

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        from lank.config import load_config
        cfg = load_config()
        self.assertIn("api_key", cfg)
        self.assertIn("auto_mode", cfg)
        self.assertIn("tool_output_limit", cfg)

    def test_cache(self):
        import lank.config as cfg
        cfg._invalidate_cache()
        c1 = cfg.load_config()
        c1["model"] = "MUTATED"   # 修改返回值，不应污染缓存
        c2 = cfg.load_config()
        self.assertNotEqual(c2["model"], "MUTATED")


class TestTools(unittest.TestCase):
    def test_registry(self):
        from lank.tools import get_all_tools, get_tool
        tools = get_all_tools()
        names = {t["function"]["name"] for t in tools}
        self.assertIn("read_file", names)
        self.assertIn("execute_command", names)
        self.assertIn("submit_plan", names)
        self.assertIn("memory_search", names)
        info = get_tool("execute_command")
        self.assertEqual(info["danger_level"], 3)
        self.assertEqual(info["approval"], "confirm")

    def test_calculate_safety(self):
        from lank.tools.system import calculate
        self.assertIn("不支持幂运算", calculate("9**9**9"))
        self.assertIn("=", calculate("2+3*4"))
        self.assertIn("过长", calculate("1" * 200))

    def test_todo_id_no_conflict(self):
        from lank.tools.todo_tools import _next_todo_id
        self.assertEqual(_next_todo_id([{"id": 1}, {"id": 3}]), 4)
        self.assertEqual(_next_todo_id([]), 1)

    def test_cmd_blacklist(self):
        from lank.tools.cmd_exec import _check_dangerous
        self.assertIsNotNone(_check_dangerous("rm -rf /"))
        self.assertIsNotNone(_check_dangerous("shutdown /s"))
        self.assertIsNone(_check_dangerous("dir"))


class TestUtils(unittest.TestCase):
    def test_trim_history(self):
        from lank.utils import trim_history
        h = [{"role": "user", "content": str(i)} for i in range(120)]
        self.assertEqual(len(trim_history(h, 100)), 100)


class TestAgentTypes(unittest.TestCase):
    def test_plan_roundtrip(self):
        from lank.agent import Plan, Step
        plan = Plan(
            goal="测试",
            steps=[Step(id=1, title="步1", action="做", acceptance="完成")],
            review_criteria="达标",
        )
        plan2 = Plan.from_dict(plan.to_dict())
        self.assertEqual(plan2.goal, "测试")
        self.assertEqual(plan2.steps[0].acceptance, "完成")


class TestAgentLoop(unittest.TestCase):
    """FakeClient 驱动端到端状态机测试（不联网）"""

    @staticmethod
    def _tool_call(name):
        return {
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "1", "type": "function",
                            "function": {"name": name, "arguments": "{}"}}],
        }

    def test_full_flow(self):
        from lank.agent import AgentLoop, AgentCallbacks
        from lank.agent.types import StepStatus

        class FakeClient:
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None):
                from lank.agent.context import get_current_loop
                from lank.tools.plan_tools import submit_plan, step_done
                loop = get_current_loop()
                if loop is not None and loop._pending_plan is None and loop.plan is None:
                    submit_plan("测试任务", [
                        {"title": "步1", "action": "做A", "acceptance": "A完成"},
                        {"title": "步2", "action": "做B", "acceptance": "B完成"},
                    ], "整体达标")
                    return True, "", None
                for s in loop.plan.steps:
                    if s.status == StepStatus.IN_PROGRESS:
                        step_done(s.id, "完成")
                        break
                return True, "ok", None

            def complete(self, messages, system_prompt=None):
                from lank.agent.context import get_current_loop
                from lank.tools.plan_tools import submit_review
                submit_review(True, "可交付")
                return True, "", None

        events = []
        loop = AgentLoop(FakeClient(), AgentCallbacks(
            on_plan_confirm=lambda p: events.append("confirm") or True,
            on_review=lambda v: events.append(f"review:{v.deliverable}"),
        ))
        result = loop.run("帮我做测试任务")
        self.assertTrue(result.success)
        self.assertEqual(result.phase.value, "review")
        self.assertTrue(all(s.status == StepStatus.DONE for s in result.plan.steps))
        self.assertIn("confirm", events)

    def test_simple_answer(self):
        from lank.agent import AgentLoop

        class SimpleClient:
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None):
                if on_text:
                    on_text("你好")
                return True, "你好", None

            def complete(self, messages, system_prompt=None):
                return True, "你好", None

        result = AgentLoop(SimpleClient()).run("你好")
        self.assertTrue(result.success)
        self.assertEqual(result.phase.value, "classify")
        self.assertIn("你好", result.response)

    def test_user_cancel(self):
        from lank.agent import AgentLoop, AgentCallbacks

        class FakeClient:
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None):
                from lank.agent.context import get_current_loop
                from lank.tools.plan_tools import submit_plan
                loop = get_current_loop()
                if loop is not None and loop._pending_plan is None and loop.plan is None:
                    submit_plan("任务", [{"title": "步1", "action": "做", "acceptance": "完成"}])
                return True, "", None

            def complete(self, messages, system_prompt=None):
                return True, "", None

        result = AgentLoop(FakeClient(), AgentCallbacks(on_plan_confirm=lambda p: False)).run("任务")
        self.assertFalse(result.success)
        self.assertEqual(result.phase.value, "plan")


class TestMemory(unittest.TestCase):
    """monkeypatch 存储路径到临时目录（不污染 ~/.lank）"""

    def setUp(self):
        self.tmp = Path(".test_mem_tmp")
        shutil.rmtree(self.tmp, ignore_errors=True)
        import lank.memory.store as ms
        self.ms = ms
        ms.MEMORY_DIR = self.tmp
        ms.HISTORY_DIR = self.tmp / "history"
        ms.SUMMARIES_FILE = self.tmp / "summaries.json"
        ms.FACTS_FILE = self.tmp / "facts.json"
        ms.PROFILE_FILE = self.tmp / "profile.json"
        ms.ensure_memory_dir()
        import lank.memory.forget as mf
        mf.HISTORY_DIR = ms.HISTORY_DIR
        mf.SUMMARIES_FILE = ms.SUMMARIES_FILE
        mf.FACTS_FILE = ms.FACTS_FILE

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_retrieval_ordering(self):
        self.ms.add_summary("s1", "2025-01-01T00:00:00",
                            "用户讨论了项目 LANK 的架构设计，采用 ReAct 框架", ["lank"], 5)
        self.ms.add_fact("用户偏好中文回复", source="explicit", importance=3)
        from lank.memory import search_memories
        r = search_memories("架构设计")
        self.assertTrue(r)
        self.assertIn("架构设计", r[0]["text"])

    def test_save_load_conversation(self):
        sid = self.ms.save_conversation([{"role": "user", "content": "你好"}])
        self.assertTrue(sid)
        loaded = self.ms.load_conversation(sid)
        self.assertEqual(loaded[0]["content"], "你好")

    def test_cleanup(self):
        self.ms.add_summary("old", "2020-01-01T00:00:00", "旧会话", [], 1)
        from lank.memory import cleanup_old_memories
        n = cleanup_old_memories(1)
        self.assertEqual(n, 0)  # 无原始会话文件
        from lank.memory.store import load_summaries
        self.assertNotIn("old", load_summaries())


if __name__ == "__main__":
    unittest.main()
