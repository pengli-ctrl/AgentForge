"""Prompt 模板管理器 — 加载、渲染、版本控制。

从 prompts/templates/ 目录加载 Prompt 模板文件，
支持变量渲染和版本管理。

设计原则：
- 模板与代码分离：Prompt 模板存放在 templates/ 目录，不硬编码在 Python 中
- 版本管理：模板文件通过 Git 进行版本控制
- 变量渲染：支持 {variable} 风格的变量替换
- 回退机制：模板不存在时使用默认模板
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class PromptManager:
    """Prompt 模板管理器 — 加载、渲染、版本控制。

    从指定目录加载 .txt 格式的 Prompt 模板文件，
    支持 {variable} 风格的变量渲染。

    Args:
        template_dir: 模板文件目录。
    """

    def __init__(self, template_dir: str = "") -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            template_dir: str，调用方传入的 template_dir 参数。

        Returns:
            None，函数执行后的结果。
        """
        if not template_dir:
            # 默认使用本模块下的 templates 目录
            template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.template_dir = template_dir
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        """加载 Prompt 模板。

        从 template_dir/{name}.txt 加载模板内容。
        加载后缓存，后续读取直接从缓存返回。

        Args:
            name: 模板名称（不含扩展名）。

        Returns:
            模板内容字符串。

        Raises:
            FileNotFoundError: 模板文件不存在时抛出。
        """
        if name in self._cache:
            return self._cache[name]

        file_path = os.path.join(self.template_dir, f"{name}.txt")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt template not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        self._cache[name] = content
        logger.debug("Prompt template loaded (name=%s, length=%d)", name, len(content))

        return content

    def render(self, name: str, **variables: Any) -> str:
        """加载并渲染 Prompt 模板。

        使用 Python str.format() 进行变量替换。
        模板中的 {variable} 会被替换为 variables 中对应的值。

        Args:
            name: 模板名称。
            **variables: 模板变量。

        Returns:
            渲染后的 Prompt 字符串。
        """
        template = self.load(name)

        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning(
                "Prompt template rendering: missing variable %s (template=%s)",
                e,
                name,
            )
            return template

    def list_templates(self) -> list[str]:
        """列出所有可用的模板名称。

        Returns:
            模板名称列表（不含扩展名）。
        """
        if not os.path.exists(self.template_dir):
            return []

        templates: list[str] = []
        for filename in os.listdir(self.template_dir):
            if filename.endswith(".txt"):
                templates.append(filename[:-4])

        return sorted(templates)

    def clear_cache(self) -> None:
        """清除模板缓存。"""
        self._cache.clear()
        logger.debug("Prompt template cache cleared")

    def get_template_info(self, name: str) -> dict[str, Any]:
        """获取模板信息。

        Args:
            name: 模板名称。

        Returns:
            包含模板名称、路径、大小的字典。
        """
        file_path = os.path.join(self.template_dir, f"{name}.txt")
        exists = os.path.exists(file_path)

        info: dict[str, Any] = {
            "name": name,
            "path": file_path,
            "exists": exists,
        }

        if exists:
            info["size"] = os.path.getsize(file_path)
            info["cached"] = name in self._cache

        return info
