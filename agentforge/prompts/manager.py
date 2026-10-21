"""管理器模块。"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class PromptManager:
    """提示词相关组件。"""

    def __init__(self, template_dir: str = "") -> None:
        """初始化 PromptManager。

        Args:
            template_dir: 模板。
        """
        if not template_dir:
            # 默认使用本模块下的 templates 目录
            template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.template_dir = template_dir
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        """加载提示词。

        Args:
            name: 资源或对象名称。

        Returns:
            字符串结果。

        Raises:
            FileNotFoundError: 操作无法完成时抛出。
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
        """渲染提示词。

        Args:
            name: 资源或对象名称。
            variables: 输入参数。

        Returns:
            字符串结果。
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
            结果列表。
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
            name: 资源或对象名称。

        Returns:
            结构化结果字典。
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
