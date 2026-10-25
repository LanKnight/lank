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

    def test_smart_truncate_keeps_head_and_tail(self):
        """首尾截断：超长时保留开头+结尾、不超预算；短文本原样返回"""
        from lank.utils import smart_truncate
        text = "H" * 100 + "M" * 2000 + "T" * 100
        out = smart_truncate(text, 200)
        self.assertLessEqual(len(out), 200)
        self.assertTrue(out.startswith("HHHH"))       # 保留开头
        self.assertTrue(out.endswith("TTTT"))         # 保留结尾（错误/退出信息常在尾部）
        self.assertIn("已截断", out)
        self.assertEqual(smart_truncate("abc", 100), "abc")   # 未超预算不截
        self.assertEqual(smart_truncate("abc", 0), "abc")     # limit<=0 不截

    def test_is_newer_version(self):
        """语义化版本比较（修复旧版字符串比较 bug）"""
        from lank.utils import is_newer_version
        self.assertTrue(is_newer_version("1.10", "1.9"))     # 字符串比较会误判
        self.assertFalse(is_newer_version("1.9", "1.10"))
        self.assertFalse(is_newer_version("1.2.3", "1.2.3"))
        self.assertTrue(is_newer_version("v2.0", "1.9.9"))
        self.assertTrue(is_newer_version("1.2.4", "1.2.3"))
        self.assertFalse(is_newer_version("", "1.0"))


class TestUsage(unittest.TestCase):
    """token 用量累加（不联网，构造假响应对象）

    隔离：拦截 record_token_usage，避免单测污染用户 ~/.lank/stats.json。
    """

    def setUp(self):
        from unittest import mock
        import lank.utils as u
        self._p = mock.patch.object(u, "record_token_usage")
        self.rec = self._p.start()

    def tearDown(self):
        self._p.stop()

    def _mk_client(self):
        from lank.ai_client import AIClient
        return AIClient()

    def test_record_usage_from_response(self):
        c = self._mk_client()

        class Usage:
            prompt_tokens = 10
            completion_tokens = 5
            total_tokens = 15

        class Resp:
            usage = Usage()

        c._record_usage(Resp())
        c._record_usage_dict({"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3})
        self.assertEqual(c.total_prompt_tokens, 11)
        self.assertEqual(c.total_completion_tokens, 7)
        self.assertEqual(c.total_tokens, 18)
        self.assertEqual(c.total_api_calls, 2)
        self.assertIn("18", c.usage_summary())

    def test_record_usage_safe_when_absent(self):
        c = self._mk_client()

        class Resp:
            usage = None

        c._record_usage(Resp())          # 无 usage 不应报错也不累加
        c._record_usage_dict(None)
        self.assertEqual(c.total_tokens, 0)
        self.assertEqual(c.total_api_calls, 0)
        self.rec.assert_not_called()

    def test_record_usage_persists_incrementally(self):
        """修复：每条有 token 的响应都增量落盘（覆盖 TUI 交互路径）"""
        c = self._mk_client()
        c._record_usage_dict({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        self.rec.assert_called_once_with(10, 5, 15)
        c._record_usage_dict({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        self.assertEqual(self.rec.call_count, 1)   # total<=0 不落盘


class TestStreamUsage(unittest.TestCase):
    """流式请求必须带 include_usage，否则流式路径 token 统计恒为 0（/stats 失真）"""

    def _mk_client(self):
        from lank.ai_client import AIClient
        return AIClient()

    def _fake(self, create):
        from types import SimpleNamespace
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def test_stream_includes_usage_option(self):
        c = self._mk_client()
        rec = []
        c.client = self._fake(lambda **kw: (rec.append(kw), object())[1])
        c._create_completion([{"role": "user", "content": "x"}], stream=True)
        self.assertEqual(rec[0].get("stream_options"), {"include_usage": True})

    def test_non_stream_has_no_stream_options(self):
        c = self._mk_client()
        rec = []
        c.client = self._fake(lambda **kw: (rec.append(kw), object())[1])
        c._create_completion([{"role": "user", "content": "x"}], stream=False)
        self.assertNotIn("stream_options", rec[0])

    def test_bad_request_falls_back_without_stream_options(self):
        import lank.ai_client as ac
        if not ac.HAS_OPENAI:
            self.skipTest("openai 未安装")
        import httpx
        resp = httpx.Response(400, request=httpx.Request("POST", "http://localhost"))
        err = ac.BadRequestError("unsupported stream_options", response=resp, body=None)
        c = self._mk_client()
        rec = []

        def create(**kw):
            rec.append(kw)
            if "stream_options" in kw:
                raise err
            return object()
        c.client = self._fake(create)
        c._create_completion([{"role": "user", "content": "x"}], stream=True)
        self.assertEqual(len(rec), 2)                 # 带参失败 → 降级重试一次
        self.assertIn("stream_options", rec[0])
        self.assertNotIn("stream_options", rec[1])

    def test_accumulate_stream_reads_usage_from_final_chunk(self):
        """从 choices 为空但带 usage 的末 chunk 取到用量"""
        from types import SimpleNamespace
        from lank.ai_client import _accumulate_stream

        class U:
            prompt_tokens = 3
            completion_tokens = 4
            total_tokens = 7

        d1 = SimpleNamespace(delta=SimpleNamespace(content="hi", tool_calls=None))
        ch1 = SimpleNamespace(choices=[d1], usage=None)
        ch2 = SimpleNamespace(choices=[], usage=U())
        content, tcs, usage = _accumulate_stream([ch1, ch2])
        self.assertEqual(content, "hi")
        self.assertEqual(tcs, [])
        self.assertEqual(usage.get("total_tokens"), 7)


class TestVector(unittest.TestCase):
    """可选向量后端：纯函数 + 默认降级（不依赖模型）"""

    def test_cosine(self):
        from lank.memory.vector import cosine
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0)
        self.assertEqual(cosine([], [1.0]), 0.0)        # 空向量
        self.assertEqual(cosine([0, 0], [1, 1]), 0.0)   # 零向量
        self.assertEqual(cosine([1, 2], [1]), 0.0)      # 长度不等

    def test_embed_disabled_returns_none(self):
        from unittest import mock
        import lank.memory.vector as v
        with mock.patch.object(v, "get_config", lambda k, d=None: False):
            self.assertIsNone(v.embed(["hello"]))
            self.assertFalse(v.enabled())


class TestStepBudget(unittest.TestCase):
    """单步上下文字符预算护栏（纯函数）"""

    def test_messages_char_len(self):
        from lank.ai_client import _messages_char_len
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": '{"path":"a"}'}}]},
        ]
        self.assertEqual(
            _messages_char_len(msgs),
            5 + len("read_file") + len('{"path":"a"}'),
        )
        self.assertEqual(_messages_char_len([]), 0)

    def test_context_budget_guard(self):
        """首轮/续轮统一的预算护栏：超限返回警告，预算<=0 禁用"""
        from unittest import mock
        import lank.ai_client as ac
        c = ac.AIClient()
        sys_msg = {"role": "system", "content": "s"}
        big = [{"role": "user", "content": "x" * 100}]
        with mock.patch.object(ac, "get_config",
                               lambda k, d=None: 50 if k == "max_step_context_chars" else d):
            self.assertIsNotNone(c._context_budget_guard(sys_msg, big))
        with mock.patch.object(ac, "get_config",
                               lambda k, d=None: 0 if k == "max_step_context_chars" else d):
            self.assertIsNone(c._context_budget_guard(sys_msg, big))


class TestLogging(unittest.TestCase):
    """终端日志开关不得误伤文件 handler（RotatingFileHandler 亦是 StreamHandler 子类）"""

    def test_set_console_logging_preserves_file_handler(self):
        import logging
        from lank import logs
        logs.setup_logging()
        root = logging.getLogger("lank")
        file_h = next((h for h in root.handlers
                       if isinstance(h, logging.FileHandler)), None)
        self.assertIsNotNone(file_h)
        before = file_h.level
        logs.set_console_logging(False)
        self.assertEqual(file_h.level, before)              # 文件 handler 级别不变
        self.assertGreater(logs._console_handler.level, logging.CRITICAL)  # 终端静默
        logs.set_console_logging(True)
        self.assertEqual(file_h.level, before)
        self.assertEqual(logs._console_handler.level, logging.WARNING)


class TestPrompts(unittest.TestCase):
    """提示词渲染对字面花括号免疫（旧 .format 会崩）"""

    def test_render_keeps_literal_braces(self):
        from lank.agent.prompts import _render
        out = _render('goal={goal} json={"a": 1} {unknown}', goal="G")
        self.assertIn("goal=G", out)
        self.assertIn('json={"a": 1}', out)     # 字面花括号原样保留
        self.assertIn("{unknown}", out)          # 未知占位符不动

    def test_exec_prompt_custom_with_braces_no_crash(self):
        from unittest import mock
        import lank.config as cfg
        custom = '目标:{goal} 示例:{"k":"v"} 完成后调 step_done'
        with mock.patch.object(cfg, "get_config",
                               lambda k, d="": custom if k == "exec_prompt" else d):
            from lank.agent.prompts import get_exec_prompt
            out = get_exec_prompt(goal="G", step_index=1, step_total=2, step_id=3,
                                  step_title="t", step_action="a", step_acceptance="acc")
            self.assertIn("目标:G", out)
            self.assertIn('{"k":"v"}', out)      # 旧 .format 在此会抛 KeyError


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
    """FakeClient 驱动端到端状态机测试（不联网）

    测试隔离：强制关闭 auto_mode/test_mode，避免被测逻辑受用户全局
    ~/.lank/config.json 影响（否则 test_mode=true 会让计划/终审自动跳过）。
    """

    def setUp(self):
        import lank.agent.loop as loop_mod
        from unittest import mock
        self._real_get_config = loop_mod.get_config

        def _get_config(key, default=None):
            if key in ("auto_mode", "test_mode"):
                return False
            return self._real_get_config(key, default)

        self._patcher = mock.patch.object(loop_mod, "get_config", _get_config)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

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
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None, system_prompt=None):
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
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None, system_prompt=None):
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
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None, system_prompt=None):
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
        ms.PROCEDURES_FILE = self.tmp / "procedures.json"
        # 重置进程内缓存，避免跨用例污染
        ms._facts_cache = None
        ms._facts_mtime = None
        ms._procs_cache = None
        ms._procs_mtime = None
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

    def test_relevant_context_budget_and_dedup(self):
        """注入：画像按 Top-K 截断、事实不重复、memory_enabled 关闭完全不注入"""
        from unittest import mock
        import lank.memory.retriever as rt
        for i in range(30):
            self.ms.add_fact(f"用户偏好事实编号{i} 主题 arch{i}", source="auto", importance=1)
        self.ms.add_fact("用户偏好中文回复 与 arch 相关", source="explicit", importance=3)
        self.ms.add_summary("s1", "2025-01-01T00:00:00", "讨论了 arch 架构设计", ["arch"], 3)

        ctx = rt.get_relevant_context("arch")
        self.assertIn("用户画像与长期记忆", ctx)
        bullet_lines = [ln for ln in ctx.splitlines() if ln.startswith("- ")]
        self.assertLessEqual(len(bullet_lines), 17)   # 画像(<=12) + 历史摘要若干
        # 去重：旧版会把同一条事实注入两次，现在只出现一次
        self.assertEqual(ctx.count("用户偏好中文回复"), 1)

        real = rt.get_config
        with mock.patch.object(
            rt, "get_config",
            lambda k, d=None: (False if k == "memory_enabled" else real(k, d)),
        ):
            self.assertEqual(rt.get_relevant_context("arch"), "")

    def test_relevant_context_char_cap(self):
        """总长安全封顶：无论多少条事实，注入文本不超过 memory_max_inject_chars"""
        from unittest import mock
        import lank.memory.retriever as rt
        long = "很长" * 80
        for i in range(40):
            self.ms.add_fact(f"事实{i}:" + long, importance=2)
        real = rt.get_config
        with mock.patch.object(
            rt, "get_config",
            lambda k, d=None: (300 if k == "memory_max_inject_chars" else real(k, d)),
        ):
            ctx = rt.get_relevant_context("事实")
        self.assertLessEqual(len(ctx), 300)

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

    def test_add_fact_near_dedup_merge(self):
        """近似去重：同义改写合并为一条，累加提及次数/取更高重要性/显式源优先"""
        fid1 = self.ms.add_fact("用户住在北京市", source="auto", importance=1)
        fid2 = self.ms.add_fact("用户住在北京市里", source="explicit", importance=2)
        self.assertEqual(fid1, fid2)
        facts = self.ms.load_facts()
        self.assertEqual(len(facts), 1)
        e = facts[fid1]
        self.assertEqual(e["mention_count"], 2)
        self.assertEqual(e["source"], "explicit")
        self.assertEqual(e["importance"], 2)

    def test_procedure_add_merge_remove(self):
        """程序性记忆：新增/目标近似重复合并(复用次数+)/删除"""
        steps = [{"title": "读取数据", "action": "read_file", "acceptance": "得到表格"}]
        pid = self.ms.add_procedure("分析葡萄酒评分", steps)
        self.assertTrue(pid)
        pid2 = self.ms.add_procedure("分析葡萄酒评分", steps)
        self.assertEqual(pid, pid2)
        self.assertEqual(self.ms.load_procedures()[pid]["use_count"], 2)
        self.assertTrue(self.ms.remove_procedure(pid))
        self.assertNotIn(pid, self.ms.load_procedures())

    def test_search_procedures_and_inject(self):
        """检索可复用流程，并在有查询时注入“可复用流程”段"""
        steps = [{"title": "解析评分表", "action": "read", "acceptance": "ok"},
                 {"title": "生成图表", "action": "plot", "acceptance": "ok"}]
        self.ms.add_procedure("葡萄酒盲测分析", steps)
        from lank.memory import search_procedures
        r = search_procedures("葡萄酒 分析")
        self.assertTrue(r)
        self.assertEqual(r[0]["kind"], "procedure")
        from lank.memory.retriever import get_relevant_context
        ctx = get_relevant_context("葡萄酒 分析")
        self.assertIn("可复用流程", ctx)
        self.assertIn("规划时请优先参考", ctx)   # 可操作的规划指引
        # 空查询不注入流程段
        self.assertNotIn("可复用流程", get_relevant_context(""))

    def test_record_procedure_on_success(self):
        """成功计划沉淀程序记忆；无 DONE 步骤不沉淀"""
        from lank.agent import AgentLoop
        from lank.agent.types import Plan, Step, StepStatus
        loop = AgentLoop(client=None)
        plan = Plan(goal="完成报表汇总", steps=[
            Step(id=1, title="读取", action="read", acceptance="ok", status=StepStatus.DONE),
            Step(id=2, title="汇总", action="sum", acceptance="ok", status=StepStatus.DONE),
        ], review_criteria="ok")
        loop._record_procedure(plan)
        self.assertTrue(self.ms.load_procedures())
        n = len(self.ms.load_procedures())
        plan2 = Plan(goal="失败任务", steps=[
            Step(id=1, title="x", action="y", acceptance="z", status=StepStatus.BLOCKED)],
            review_criteria="")
        loop._record_procedure(plan2)
        self.assertEqual(len(self.ms.load_procedures()), n)

    def test_export_import_memories(self):
        """导出快照→清空→导入回灌（逐条 add_* 去重），计数正确"""
        from lank.memory import export_memories, import_memories
        self.ms.add_fact("导出测试事实甲", source="explicit", importance=2)
        pid = self.ms.add_procedure(
            "导出流程目标", [{"title": "步骤A", "action": "a", "acceptance": "ok"}])
        self.assertTrue(pid)
        path = export_memories(str(self.tmp / "backup.json"))
        self.assertTrue(Path(path).exists())
        # 清空当前记忆（删文件+重置缓存）
        self.ms.FACTS_FILE.unlink(missing_ok=True)
        self.ms.PROCEDURES_FILE.unlink(missing_ok=True)
        self.ms._facts_cache = None
        self.ms._facts_mtime = None
        self.ms._procs_cache = None
        self.ms._procs_mtime = None
        self.assertEqual(len(self.ms.load_facts()), 0)
        c = import_memories(path)
        self.assertEqual(c["facts"], 1)
        self.assertEqual(c["procedures"], 1)
        self.assertEqual(len(self.ms.load_facts()), 1)
        self.assertEqual(len(self.ms.load_procedures()), 1)

    def test_import_missing_file_safe(self):
        """导入不存在/非法文件：返回 error 计数且不抛异常"""
        from lank.memory import import_memories
        c = import_memories(str(self.tmp / "nonexist.json"))
        self.assertEqual(c["error"], 1)
        self.assertEqual(c["facts"], 0)

    def test_memory_search_tool_includes_procedure(self):
        """agent 主动回忆工具 memory_search 能取到第4层可复用流程"""
        self.ms.add_procedure(
            "记忆搜索流程验收", [{"title": "步A", "action": "a", "acceptance": "ok"}])
        from lank.tools.memory_tools import memory_search
        r = memory_search("记忆搜索流程验收")
        self.assertIn("流程", r)

    def test_import_overwrite_mode(self):
        """overwrite 模式：先清空本地事实/流程再回灌快照（旧内容不再残留）"""
        import json
        from lank.memory import import_memories
        self.ms.add_fact("本地旧事实", source="auto")
        self.ms.add_procedure("本地旧流程",
                              [{"title": "旧", "action": "x", "acceptance": "y"}])
        snap = self.tmp / "snap.json"
        snap.write_text(json.dumps({
            "facts": {"fact_1": {"text": "快照事实A", "source": "explicit", "importance": 3}},
            "procedures": {"proc_1": {"goal": "快照流程B",
                                      "steps": [{"title": "B", "action": "b", "acceptance": "ok"}],
                                      "keywords": [], "review_criteria": ""}},
            "summaries": {},
        }, ensure_ascii=False), encoding="utf-8")
        c = import_memories(str(snap), mode="overwrite")
        self.assertEqual(c["facts"], 1)
        self.assertEqual(c["procedures"], 1)
        facts_text = " ".join(e.get("text", "") for e in self.ms.load_facts().values())
        self.assertIn("快照事实A", facts_text)
        self.assertNotIn("本地旧事实", facts_text)   # 旧事实已被清空
        self.assertEqual(len(self.ms.load_procedures()), 1)


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
        """cursor 锚定滚动：回看时锚点行上移，新消息不打断回看、底部时自动跟随"""
        app = self._make_app()
        for i in range(6):
            app._add_message("user" if i % 2 == 0 else "assistant", f"消息 {i} 内容")

        app._back_lines = 0
        bottom_y = app._get_cursor_position().y
        app._back_lines = 50
        top_y = app._get_cursor_position().y
        self.assertLess(top_y, bottom_y)          # 回看：锚点移向顶部
        self.assertEqual(top_y, 0)                # 回看够多 → 顶部

        app._add_message("system", "新消息")
        self.assertEqual(app._back_lines, 50)     # 回看中：新消息不打断（修复 #6）
        self.assertEqual(app._get_cursor_position().y, 0)  # 锚点仍在顶部

        app._back_lines = 0                       # 用户回到底部
        app._add_message("system", "再来一条")
        self.assertEqual(app._back_lines, 0)      # 底部时自动跟随最新
        self.assertGreater(app._get_cursor_position().y, bottom_y)

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

    def test_history_resume_commands(self):
        """/history 与 /resume：恢复历史会话到消息区"""
        import json
        from pathlib import Path
        app = self._make_app()

        # 构造一个临时会话文件（monkeypatch 存储路径到 workspace 临时目录）
        tmp = Path(".test_hist_tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        import lank.memory.store as ms
        ms.HISTORY_DIR = tmp / "history"
        ms.MEMORY_DIR = tmp
        ms.SUMMARIES_FILE = tmp / "summaries.json"
        ms.FACTS_FILE = tmp / "facts.json"
        ms.PROFILE_FILE = tmp / "profile.json"
        ms.ensure_memory_dir()

        sid = ms.save_conversation([
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你？"},
        ])
        self.assertTrue(sid)

        app._handle_command("/resume " + sid)
        texts = [t for _, t in app.messages]
        self.assertTrue(any("已恢复会话" in t for t in texts))
        self.assertEqual(len(app.ai_history), 2)   # user + assistant 恢复
        self.assertEqual(app.session_id, sid)

        app._handle_command("/history")
        texts = [t for _, t in app.messages]
        self.assertTrue(any("最近会话" in t for t in texts))

        shutil.rmtree(tmp, ignore_errors=True)

    def test_scroll_no_crash_long_output(self):
        """回归：长 tool 输出 + 大回看偏移，锚点永不越界（曾崩溃 list index out of range）"""
        app = self._make_app()
        for i in range(40):
            app._add_message("user" if i % 2 == 0 else "assistant", f"第{i}条消息")
        app._add_message("tool", "\n".join(f"line{n}" for n in range(500)))

        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.formatted_text.utils import split_lines
        for bl in (0, 10, 100, 500, 10 ** 6):
            app._back_lines = bl
            with app._lock:
                n_lines = len(list(split_lines(FormattedText(app._build_render_items()))))
            cp = app._get_cursor_position()
            self.assertLess(cp.y, n_lines)
            self.assertGreaterEqual(cp.y, 0)
        # 底部锚点 = 最后一行
        app._back_lines = 0
        with app._lock:
            n_lines = len(list(split_lines(FormattedText(app._build_render_items()))))
        self.assertEqual(app._get_cursor_position().y, n_lines - 1)

    def test_history_empty(self):
        app = self._make_app()
        app._handle_command("/resume nonexist_session_xyz")
        texts = [t for _, t in app.messages]
        self.assertTrue(any("未找到会话" in t for t in texts))

    def test_memory_command(self):
        """/memory list/search/forget 子命令"""
        import lank.memory.store as ms
        tmp = Path(".test_cmd_mem")
        shutil.rmtree(tmp, ignore_errors=True)
        ms.MEMORY_DIR = tmp
        ms.HISTORY_DIR = tmp / "history"
        ms.SUMMARIES_FILE = tmp / "summaries.json"
        ms.FACTS_FILE = tmp / "facts.json"
        ms.PROFILE_FILE = tmp / "profile.json"
        ms.PROCEDURES_FILE = tmp / "procedures.json"
        ms._facts_cache = None
        ms._facts_mtime = None
        ms._procs_cache = None
        ms._procs_mtime = None
        ms.ensure_memory_dir()
        try:
            fid = ms.add_fact("测试记忆事实 ABC", source="explicit")
            app = self._make_app()
            app._handle_command("/memory list")
            texts = " ".join(t for _, t in app.messages)
            self.assertIn("记忆总览", texts)
            self.assertIn(fid, texts)
            app._handle_command("/memory search ABC")
            texts = " ".join(t for _, t in app.messages)
            self.assertIn("测试记忆事实", texts)
            app._handle_command("/memory forget " + fid)
            self.assertNotIn(fid, ms.load_facts())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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
            def chat(self, messages, stream=True, on_tool_call=None, on_text=None, system_prompt=None):
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
