"""
文件操作工具 - 读/写/搜索文件
类似 Claude 的文件操作能力
"""

import os
import re
import pathlib
from typing import List, Optional

from . import register_tool


def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """读取文件内容
    
    Args:
        path: 文件路径（相对或绝对路径）
        start_line: 起始行号（1-based，可选）
        end_line: 结束行号（1-based，可选）
    
    Returns:
        文件内容
    """
    try:
        resolved_path = _resolve_path(path)
        if not resolved_path.exists():
            return f"错误: 文件不存在: {path}"
        if not resolved_path.is_file():
            return f"错误: 路径不是文件: {path}"
        
        with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        if start_line is not None or end_line is not None:
            start = (start_line or 1) - 1
            end = end_line or total_lines
            lines = lines[start:end]
        
        # 添加行号
        result = []
        line_num = start_line or 1
        for line in lines:
            result.append(f"{line_num} | {line.rstrip()}")
            line_num += 1
        
        content = "\n".join(result)
        info = f"文件: {resolved_path} ({total_lines} 行)"
        if start_line or end_line:
            info += f" [显示 {start_line or 1}-{end_line or total_lines}]"
        
        return f"{info}\n{'-' * 40}\n{content}"
    except Exception as e:
        return f"读取文件失败: {e}"


def write_to_file(path: str, content: str) -> str:
    """写入文件（创建新文件或覆盖已有文件）
    
    Args:
        path: 文件路径
        content: 文件内容
    
    Returns:
        操作结果
    """
    try:
        resolved_path = _resolve_path(path)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return f"✅ 已写入文件: {resolved_path} ({len(content)} 字符)"
    except Exception as e:
        return f"写入文件失败: {e}"


def replace_in_file(path: str, search: str, replace: str) -> str:
    """在文件中替换内容（精确匹配替换）
    
    Args:
        path: 文件路径
        search: 要搜索的文本
        replace: 替换后的文本
    
    Returns:
        操作结果
    """
    try:
        resolved_path = _resolve_path(path)
        if not resolved_path.exists():
            return f"错误: 文件不存在: {path}"
        
        with open(resolved_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if search not in content:
            return f"错误: 未找到匹配内容"
        
        count = content.count(search)
        new_content = content.replace(search, replace, 1)  # 只替换第一个匹配
        
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        return f"✅ 已替换文件: {resolved_path} (替换了 {count} 处匹配中的第 1 处)"
    except Exception as e:
        return f"替换文件内容失败: {e}"


def search_files(path: str, pattern: str, file_pattern: Optional[str] = None) -> str:
    """在目录中搜索文件内容
    
    Args:
        path: 搜索目录路径
        pattern: 正则表达式模式
        file_pattern: 文件通配符模式（如 *.py），可选
    
    Returns:
        搜索结果
    """
    try:
        resolved_path = _resolve_path(path)
        if not resolved_path.exists():
            return f"错误: 目录不存在: {path}"
        if not resolved_path.is_dir():
            return f"错误: 路径不是目录: {path}"
        
        results = []
        regex = re.compile(pattern)
        
        for root, dirs, files in os.walk(resolved_path):
            # 跳过隐藏目录和 __pycache__
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for filename in files:
                if file_pattern and not pathlib.PurePath(filename).match(file_pattern):
                    continue
                
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line.rstrip()):
                                rel_path = os.path.relpath(filepath, resolved_path)
                                results.append(f"{rel_path}:{i}: {line.rstrip()}")
                except (IOError, UnicodeDecodeError):
                    continue
        
        if not results:
            return f"在 {resolved_path} 中未找到匹配 '{pattern}' 的内容"
        
        # 限制结果数量
        if len(results) > 100:
            summary = f"找到 {len(results)} 个匹配 (显示前 100 个):\n"
            results = results[:100]
        else:
            summary = f"找到 {len(results)} 个匹配:\n"
        
        return summary + "\n".join(results)
    except Exception as e:
        return f"搜索文件失败: {e}"


def list_files(path: str, recursive: bool = False) -> str:
    """列出目录内容
    
    Args:
        path: 目录路径
        recursive: 是否递归列出
    
    Returns:
        目录列表
    """
    try:
        resolved_path = _resolve_path(path)
        if not resolved_path.exists():
            return f"错误: 路径不存在: {path}"
        if not resolved_path.is_dir():
            return f"错误: 路径不是目录: {path}"
        
        items = []
        if recursive:
            for root, dirs, files in os.walk(resolved_path):
                # 跳过隐藏目录和 __pycache__
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                rel_root = os.path.relpath(root, resolved_path)
                if rel_root == ".":
                    for f in files:
                        if not f.startswith('.'):
                            items.append(f"📄 {f}")
                    for d in dirs:
                        items.append(f"📁 {d}/")
                else:
                    for f in files:
                        if not f.startswith('.'):
                            items.append(f"📄 {rel_root}/{f}")
                    for d in dirs:
                        items.append(f"📁 {rel_root}/{d}/")
        else:
            for entry in sorted(resolved_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                if entry.name.startswith('.'):
                    continue
                if entry.is_dir():
                    items.append(f"📁 {entry.name}/")
                else:
                    items.append(f"📄 {entry.name}")
        
        if not items:
            return f"目录为空: {resolved_path}"
        
        return f"目录: {resolved_path}\n{'=' * 40}\n" + "\n".join(items)
    except Exception as e:
        return f"列出目录失败: {e}"


def list_code_definition_names(path: str) -> str:
    """列出源代码中的定义名称（类、函数等）
    
    Args:
        path: 目录路径
    
    Returns:
        代码定义列表
    """
    try:
        resolved_path = _resolve_path(path)
        if not resolved_path.exists():
            return f"错误: 路径不存在: {path}"
        
        definitions = []
        
        # 支持的文件类型
        source_extensions = {'.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp', '.go', '.rs', '.rb'}
        
        if resolved_path.is_file():
            paths = [resolved_path]
        else:
            paths = []
            for ext in source_extensions:
                paths.extend(resolved_path.rglob(f"*{ext}"))
        
        for filepath in paths:
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                rel_path = filepath.relative_to(resolved_path.parent) if resolved_path.is_file() else filepath.relative_to(resolved_path)
                
                # Python 定义
                if filepath.suffix == '.py':
                    for match in re.finditer(r'^(?:class|def|async\s+def)\s+(\w+)', content, re.MULTILINE):
                        definitions.append(f"{rel_path}: {match.group(0)}")
                
                # 其他语言的基本匹配
                elif filepath.suffix in {'.js', '.ts'}:
                    for match in re.finditer(r'(?:function|class|const\s+\w+\s*=\s*(?:async\s*)?\(|export\s+(?:default\s+)?(?:function|class|const))\s*(\w+)', content):
                        definitions.append(f"{rel_path}: {match.group(0)}")
                
            except (IOError, UnicodeDecodeError):
                continue
        
        if not definitions:
            return f"在 {resolved_path} 中未找到代码定义"
        
        return f"代码定义 ({len(definitions)} 个):\n" + "\n".join(definitions)
    except Exception as e:
        return f"列出代码定义失败: {e}"


def _resolve_path(path: str) -> pathlib.Path:
    """解析路径（支持相对路径和绝对路径）"""
    p = pathlib.Path(path)
    if p.is_absolute():
        return p
    # 相对于当前工作目录
    return pathlib.Path.cwd() / p


# ===== 注册工具 =====

register_tool(
    name="read_file",
    description="读取文件内容，可指定行范围",
    func=read_file,
    parameters=[
        {"name": "path", "type": "string", "description": "文件路径"},
        {"name": "start_line", "type": "integer", "description": "起始行号（可选）", "required": False},
        {"name": "end_line", "type": "integer", "description": "结束行号（可选）", "required": False},
    ],
)

register_tool(
    name="write_to_file",
    description="创建新文件或覆盖已有文件",
    func=write_to_file,
    parameters=[
        {"name": "path", "type": "string", "description": "文件路径"},
        {"name": "content", "type": "string", "description": "文件内容"},
    ],
    requires_approval=True,
)

register_tool(
    name="replace_in_file",
    description="在文件中精确匹配并替换文本",
    func=replace_in_file,
    parameters=[
        {"name": "path", "type": "string", "description": "文件路径"},
        {"name": "search", "type": "string", "description": "要搜索的文本"},
        {"name": "replace", "type": "string", "description": "替换后的文本"},
    ],
    requires_approval=True,
)

register_tool(
    name="search_files",
    description="在目录中搜索匹配正则表达式的文件内容",
    func=search_files,
    parameters=[
        {"name": "path", "type": "string", "description": "搜索目录路径"},
        {"name": "pattern", "type": "string", "description": "正则表达式模式"},
        {"name": "file_pattern", "type": "string", "description": "文件通配符（如 *.py），可选", "required": False},
    ],
)

register_tool(
    name="list_files",
    description="列出目录中的文件和子目录",
    func=list_files,
    parameters=[
        {"name": "path", "type": "string", "description": "目录路径"},
        {"name": "recursive", "type": "boolean", "description": "是否递归列出", "required": False},
    ],
)

register_tool(
    name="list_code_definition_names",
    description="列出源代码文件中的类、函数等定义名称",
    func=list_code_definition_names,
    parameters=[
        {"name": "path", "type": "string", "description": "目录或文件路径"},
    ],
)
