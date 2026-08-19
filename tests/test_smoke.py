"""
冒烟测试 - 覆盖核心模块的关键行为（unittest，零新依赖）

运行: python -m unittest discover -s tests -v
"""

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from prompt_toolkit.output import DummyOutput
except ImportError:
    DummyOutput = None  # type: ignore


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


class TestChatApp(unittest.TestCase):
    """全屏聊天界面纯逻辑测试（不启动真实终端）"""

    def _make_app(self):
        from lank.tui import ChatApp
        app = ChatApp(ai_only=False)
        app._build_pt(output=DummyOutput())
        return app

    def test_command_handling(self):
        app = self._make_app()
        app._handle_command("/help")
        app._handle_command("/normal")
        app._handle_command("/unknownxx")
        texts = " ".join(t for _, t in app.messages)
        self.assertIn("可用命令", texts)
        self.assertIn("未知命令", texts)

    def test_scroll_anchor(self):
        """cursor 锚定滚动：回看时锚点上移，新消息重置回底部"""
        app = self._make_app()
        for i in range(6):
            app._add_message("user" if i % 2 == 0 else "assistant", f"消息 {i} 内容")

        def anchor_line(ft):
            pos = 0
            for style, text in ft:
                if style == "[SetCursorPosition]":
                    return pos
                pos += text.count("\n") + 1
            return -1

        app._back_lines = 0
        bottom = anchor_line(app._render_messages())
        app._back_lines = 50
        top = anchor_line(app._render_messages())
        self.assertLess(top, bottom)          # 回看：锚点移向顶部
        app._add_message("system", "新消息")
        self.assertEqual(app._back_lines, 0)  # 新消息：重置回底部

    def test_ask_bridge(self):
        """AI 线程提问 ↔ UI 线程回答 桥接"""
        import threading
        app = self._make_app()
        result = {}

        def ask_thread():
            result["ans"] = app.ask_user_sync("测试问题")

        t = threading.Thread(target=ask_thread)
        t.start()
        import time
        time.sleep(0.3)
        self.assertIsNotNone(app._pending_ask)
        app._on_accept(type("B", (), {"text": "回答A", "reset": lambda s: None})())
        t.join(3)
        self.assertEqual(result.get("ans"), "回答A")
        self.assertIsNone(app._pending_ask)

    def test_confirm_bridge(self):
        import threading
        app = self._make_app()
        result = {}

        def c_thread():
            result["ok"] = app.confirm_sync("是否允许?")

        t = threading.Thread(target=c_thread)
        t.start()
        import time
        time.sleep(0.3)
        app._on_accept(type("B", (), {"text": "n", "reset": lambda s: None})())
        t.join(3)
        self.assertFalse(result.get("ok"))

    def test_complex_task_full_flow(self):
        """复杂任务全流程：进度/工具/交付总结，且最终消息不是碎片拼接"""
        import threading
        import time
        from lank.agent.types import StepStatus
        app = self._make_app()
        app.ai_available = True

        class FakeClient:
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None):
                from lank.agent.context import get_current_loop
                from lank.tools.plan_tools import submit_plan, step_done
                loop = get_current_loop()
                if loop is not None and loop._pending_plan is None and loop.plan is None:
                    if on_text:
                        on_text("[plan] 我来规划。")
                    submit_plan("复杂任务", [
                        {"title": "步骤1", "action": "读", "acceptance": "读完"},
                        {"title": "步骤2", "action": "写", "acceptance": "写完"},
                    ], "整体完成")
                    return True, "[plan] 我来规划。", None
                for s in loop.plan.steps:
                    if s.status == StepStatus.IN_PROGRESS:
                        if on_tool_call:
                            ok = on_tool_call("execute_command", {"command": "dir"})
                            if ok:
                                on_tool_call("execute_command", {"command": "dir"}, "目录结果")
                        step_done(s.id, f"{s.title}完成")
                        break
                return True, "ok", None

            def complete(self, messages, system_prompt=None, timeout=None, retry=None):
                from lank.agent.context import get_current_loop
                from lank.tools.plan_tools import submit_review
                submit_review(True, "任务完成，可以交付")
                return True, "", None

        app.client = FakeClient()
        t = threading.Thread(target=app._run_ai, args=("复杂任务",), daemon=True)
        t.start()
        deadline = time.time() + 5
        while t.is_alive() and time.time() < deadline:
            time.sleep(0.1)
            if app._pending_ask is not None:
                app._on_accept(type("B", (), {"text": "y", "reset": lambda s: None})())
        t.join(5)

        texts = "|".join(text for _, text in app.messages)
        self.assertIn("⏳ [步骤 1]", texts)                 # 步骤进度
        self.assertIn("✅ [步骤 1]", texts)                 # 步骤完成
        self.assertIn("正在执行工具", texts)                # 工具执行中
        self.assertIn("目录结果", texts)                    # 工具结果
        final = [text for r, text in app.messages if r == "assistant"]
        self.assertTrue(final)                             # 有最终消息
        self.assertEqual(final[-1].strip(), "任务完成，可以交付")  # 交付总结
        self.assertNotIn("[plan]", final[-1])              # 不是碎片拼接


if __name__ == "__main__":
    unittest.main()
