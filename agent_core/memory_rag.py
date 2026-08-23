"""记忆检索（任务 4.4）：MEMORY.md 按条目建索引，每轮按当前话题检索 Top-K 注入。

全量注入的问题：MEMORY.md 随使用线性膨胀，每轮请求的 system prompt 跟着膨胀，
token 成本线性上涨，最终撑爆上下文窗口。
检索注入（RAG）：每轮只把与当前话题最相关的 K 条放进 prompt，prompt 体积恒定。

向量来源（Vectorizer）可插拔，两种实现接口一致：
- LexicalVectorizer：本地字符二元组（bigram）词袋 + 余弦相似度。零依赖、离线可用、
  中文友好；局限是"字面相似"而非"语义相似"（同义改写可能漏检）。
  当前供应商 DeepSeek 未开放 embeddings 接口（探测 404），故为默认方案。
- APIVectorizer：在 .env 配置 LLM_EMBEDDING_MODEL=模型名 后启用，调用 OpenAI
  兼容 embeddings 接口做真语义检索；失败时自动降级为词法方案并只提示一次。

混合策略：记忆条目数 <= TRIGGER 时不检索、原样全量注入——小记忆检索没有收益，
反而可能漏条目；超过阈值才启用检索。注意 memory_compact（压缩器）始终读全量文件：
改写记忆必须看到完整原文，检索只服务于"往 prompt 里放什么"。
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter

from .llm import client as _llm_client
from .memory import MEMORY

TOP_K = int(os.environ.get("AGENT_RAG_TOP_K", "8"))
TRIGGER_ENTRIES = int(os.environ.get("AGENT_RAG_TRIGGER", "30"))


def _counter_cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[x] * b[x] for x in (set(a) & set(b)))
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _list_cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class LexicalVectorizer:
    """字符 bigram 词袋：中文按字切分比按词切分更稳（不需要分词器）。"""

    def vectorize(self, text: str) -> Counter:
        cleaned = re.sub(r"\s+", "", text.lower())
        return Counter(cleaned[i:i + 2] for i in range(len(cleaned) - 1)) or Counter(cleaned[:1])

    @staticmethod
    def similarity(va: Counter, vb: Counter) -> float:
        return _counter_cosine(va, vb)


class APIVectorizer:
    """OpenAI 兼容 embeddings 接口。首次失败由 MemoryRetriever 捕获并降级。"""

    def __init__(self, client, model: str):
        self._client = client
        self.model = model

    def vectorize(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self.model, input=[text])
        return [float(x) for x in resp.data[0].embedding]

    @staticmethod
    def similarity(va: list[float], vb: list[float]) -> float:
        return _list_cosine(va, vb)


class MemoryRetriever:
    """MEMORY.md 检索器：条目索引 + 相似度 Top-K，带内容哈希缓存。"""

    def __init__(self, memory_store, client=None, top_k: int | None = None,
                 trigger: int | None = None, vectorizer=None):
        self.memory_store = memory_store
        self._client = client
        self.top_k = top_k if top_k is not None else TOP_K
        self.trigger = trigger if trigger is not None else TRIGGER_ENTRIES
        # vectorizer 参数用于测试注入；生产路径按 env 决定（LLM_EMBEDDING_MODEL）
        self._vectorizer = vectorizer or self._make_vectorizer()
        self._cache_key = None
        self._entries: list[str] = []
        self._vectors: list = []

    def _make_vectorizer(self):
        model = os.environ.get("LLM_EMBEDDING_MODEL", "")
        if model and self._client is not None:
            return APIVectorizer(self._client, model)
        return LexicalVectorizer()

    def _degrade_to_lexical(self) -> None:
        if isinstance(self._vectorizer, LexicalVectorizer):
            return
        print("[memory_rag] embeddings 接口不可用，已降级为本地词法检索（字面相似）。")
        self._vectorizer = LexicalVectorizer()
        self._cache_key = None  # 向量类型变了，索引必须重建

    def _load_index(self) -> None:
        """解析 MEMORY.md 并建索引；内容或向量器变了才重建（压缩器随时会重写该文件）。"""
        text = self.memory_store.read_memory()
        key = (hash(text), type(self._vectorizer).__name__)
        if key == self._cache_key:
            return
        entries = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            entries.append(s.lstrip("-* ").strip())
        self._entries = entries
        try:
            self._vectors = [self._vectorizer.vectorize(e) for e in entries]
        except Exception:
            self._degrade_to_lexical()
            self._vectors = [self._vectorizer.vectorize(e) for e in entries]
            key = (hash(text), type(self._vectorizer).__name__)
        self._cache_key = key

    def retrieve(self, query: str, top_k: int | None = None) -> list[str]:
        """与 query 最相关的记忆条目（相似度降序）；条目数不超过阈值时返回全部。"""
        self._load_index()
        if not self._entries:
            return []
        if len(self._entries) <= self.trigger:
            return list(self._entries)
        try:
            qv = self._vectorizer.vectorize(query)
            sim = self._vectorizer.similarity
            scored = sorted(
                ((sim(qv, v), i, e) for i, (v, e) in enumerate(zip(self._vectors, self._entries))),
                key=lambda t: t[0], reverse=True,
            )
        except Exception:
            self._degrade_to_lexical()
            return self.retrieve(query, top_k)
        k = min(top_k or self.top_k, len(self._entries))
        return [e for s, _, e in scored[:k] if s > 0]

    def render_for_prompt(self, query: str) -> str:
        """生成注入 system prompt 的记忆块。

        记忆很小时原样返回全量文件（与旧版行为一致）；大记忆只返回 Top-K。
        """
        self._load_index()
        if len(self._entries) <= self.trigger:
            return self.memory_store.read_memory()
        hits = self.retrieve(query)
        if not hits:
            return f"(长期记忆共 {len(self._entries)} 条，暂无与当前话题明显相关的条目)"
        head = f"(长期记忆共 {len(self._entries)} 条，以下为与当前话题最相关的 {len(hits)} 条)\n"
        return head + "\n".join(f"- {h}" for h in hits)


MEMORY_RAG = MemoryRetriever(MEMORY, client=_llm_client)
