"""
Knowledge Retriever — TF-IDF cosine similarity (default) + optional embeddings.

Loads from data/knowledge_base.json if present, otherwise falls back to a
minimal built-in. The TF-IDF path is fast, lightweight, and works with no
extra dependencies — ideal for Railway free tier.
"""
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    content: str
    title: str
    category: str
    disaster_type: str
    score: float
    source: str
    metadata: Optional[Dict] = None


class KnowledgeRetriever:
    """Retrieves relevant disaster safety guidance.

    Default mode: TF-IDF + cosine similarity over the knowledge base. Fast,
    reasonable recall, no heavy deps.

    Optional mode: sentence-transformer embeddings (when the package is
    available AND `use_embeddings=True`). Higher recall, much higher memory.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        score_threshold: float = 0.15,
        use_embeddings: bool = False,
    ):
        self.model_name = model_name
        self.score_threshold = score_threshold
        self.use_embeddings = use_embeddings

        self.knowledge_base: List[Dict] = []
        self.model = None
        self.embeddings: Optional[np.ndarray] = None
        self._tfidf: Optional[TfidfVectorizer] = None
        self._tfidf_matrix = None

        self._load_knowledge_base()

        if self.use_embeddings:
            self._initialize_embeddings()

        # Always build the TF-IDF index (used as fallback OR primary).
        self._build_tfidf_index()

    # ─── Load KB ──────────────────────────────────────────────────────────────
    def _load_knowledge_base(self) -> None:
        """
        Phase 2 (v2 schema): KB is now wrapped in
        ``{"version": "2.0.0", "updated_at": ..., "entries": [...]}``.

        Phase 1 (v1 schema): KB was a flat array.

        For deployment safety we accept both shapes — Phase 2 ships the v2
        rewrite, but if a future hotfix reverts to v1 the retriever still
        works.
        """
        kb_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "knowledge_base.json"
        )
        if os.path.exists(kb_path):
            try:
                with open(kb_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "entries" in raw:
                    self.knowledge_base = raw["entries"]
                    self.kb_version = raw.get("version", "unknown")
                elif isinstance(raw, list):
                    self.knowledge_base = raw
                    self.kb_version = "1.x"
                else:
                    raise ValueError("knowledge_base.json: unrecognised shape")
                logger.info(
                    "Loaded %d KB entries (version=%s)",
                    len(self.knowledge_base),
                    self.kb_version,
                )
                return
            except Exception as e:
                logger.warning(f"Failed to load knowledge_base.json: {e}")

        # Built-in minimal fallback (only triggered if data file is missing).
        self.knowledge_base = self._builtin_minimal()
        self.kb_version = "fallback"
        logger.info(
            f"Using built-in fallback KB ({len(self.knowledge_base)} entries)"
        )

    def _searchable(self, entry: Dict) -> str:
        """Build the text we vectorise / embed for retrieval."""
        return (
            (entry.get("searchable_text") or "")
            + " "
            + (entry.get("title") or "")
            + " "
            + (entry.get("content") or "")
        ).strip()

    # ─── Embedding path ───────────────────────────────────────────────────────
    def _initialize_embeddings(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.model_name)
            texts = [self._searchable(e) for e in self.knowledge_base]
            if texts:
                self.embeddings = self.model.encode(texts, convert_to_numpy=True)
                logger.info(
                    f"Embeddings computed for {len(texts)} KB entries"
                )
        except ImportError:
            logger.info("sentence-transformers not installed — using TF-IDF")
            self.use_embeddings = False
        except Exception as e:
            logger.error(f"Failed to initialise embeddings: {e}")
            self.use_embeddings = False

    # ─── TF-IDF path (default) ────────────────────────────────────────────────
    def _build_tfidf_index(self) -> None:
        try:
            texts = [self._searchable(e) for e in self.knowledge_base]
            if not texts:
                return
            self._tfidf = TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=10000,
                stop_words="english",
                sublinear_tf=True,
                lowercase=True,
            )
            self._tfidf_matrix = self._tfidf.fit_transform(texts)
            logger.info("TF-IDF index built over %d KB entries", len(texts))
        except Exception as e:
            logger.error(f"Failed to build TF-IDF index: {e}")
            self._tfidf = None
            self._tfidf_matrix = None

    # ─── Retrieve ─────────────────────────────────────────────────────────────
    def retrieve(
        self,
        query: str,
        disaster_type: Optional[str] = None,
        category: Optional[str] = None,
        top_k: int = 3,
        *,
        phase: Optional[str] = None,
        topic: Optional[str] = None,
        disaster_types: Optional[List[str]] = None,
        include_general: bool = True,
    ) -> List[RetrievalResult]:
        """
        Retrieve top-k passages.

        Filter knobs (all optional, all combinable):
        - ``disaster_type`` — single disaster filter (legacy v1 ergonomic).
          When set, ``general`` entries also match (per the long-standing
          behaviour), unless ``include_general=False``.
        - ``disaster_types`` — explicit list of disaster types to allow.
          Use ``["general"]`` (with ``include_general=False``) to retrieve
          ONLY general-bucket entries — this is the audit B11 fix used by
          the first-aid handler so general entries don't dilute LLM
          grounding for disaster-specific queries.
        - ``category`` — legacy v1 facet name (mapped to v2 ``phase``).
        - ``phase`` — v2 phase filter (prevention/before/during/after/recovery/general).
        - ``topic`` — v2 topic facet (currently only ``first_aid``).
        - ``include_general`` — when False, the implicit "general entries are
          always allowed" rule is OFF. Explicit ``disaster_types`` filtering
          becomes strict.
        """
        if (
            self.use_embeddings
            and self.model is not None
            and self.embeddings is not None
        ):
            search = self._semantic_search
        elif self._tfidf is not None and self._tfidf_matrix is not None:
            search = self._tfidf_search
        else:
            search = self._keyword_search
        return search(
            query,
            disaster_type=disaster_type,
            category=category,
            top_k=top_k,
            phase=phase,
            topic=topic,
            disaster_types=disaster_types,
            include_general=include_general,
        )

    def _filter_indices(
        self,
        disaster_type: Optional[str],
        category: Optional[str],
        *,
        phase: Optional[str] = None,
        topic: Optional[str] = None,
        disaster_types: Optional[List[str]] = None,
        include_general: bool = True,
    ) -> List[int]:
        """
        Resolve all entry indices that match the combined filter.

        v2 entries have ``phase`` (and optional ``topic``). v1 entries had
        ``category``. The two are unified here:

        - ``phase`` matches against ``entry.phase`` first, falling back to
          ``entry.category`` for back-compat.
        - The legacy ``category="first_aid"`` is rewritten into
          ``topic="first_aid"`` because v2 separates phase from topic.
        """
        # Legacy ergonomic: category="first_aid" → topic="first_aid"
        if category == "first_aid" and topic is None:
            topic = "first_aid"
            category = None
        # v2 phase ergonomic: prefer the explicit phase arg
        effective_phase = phase or category

        # Audit B11: explicit disaster_types filter is strict — does NOT
        # implicitly admit "general" unless include_general is left at True.
        # Use disaster_types=["general"] + include_general=False to retrieve
        # ONLY the general bucket.
        explicit_dt_filter: Optional[set[str]] = (
            {dt for dt in disaster_types} if disaster_types else None
        )

        out: List[int] = []
        for i, entry in enumerate(self.knowledge_base):
            entry_dt = entry.get("disaster_type")

            # Disaster filtering
            if explicit_dt_filter is not None:
                if entry_dt not in explicit_dt_filter:
                    if not (include_general and entry_dt == "general"):
                        continue
            elif disaster_type:
                if entry_dt != disaster_type:
                    if not (include_general and entry_dt == "general"):
                        continue

            # Phase / category filter (with v1↔v2 fallback)
            if effective_phase is not None:
                entry_phase = entry.get("phase") or entry.get("category")
                if entry_phase != effective_phase:
                    continue

            # Topic filter (v2 only)
            if topic is not None:
                if entry.get("topic") != topic:
                    continue

            out.append(i)
        return out

    def _result_from_entry(self, entry: Dict, score: float) -> RetrievalResult:
        """
        Convert a v1 or v2 entry into a uniform RetrievalResult. v2 entries
        have ``phase`` and ``sources`` (list); v1 had ``category`` and
        ``source`` (string). The ``category`` field on RetrievalResult is
        kept as the v1-shaped string to preserve back-compat with handlers
        that still read it.
        """
        category = entry.get("category") or entry.get("phase") or "general"
        sources = entry.get("source")
        if not sources:
            v2_sources = entry.get("sources") or []
            if isinstance(v2_sources, list):
                sources = "; ".join(
                    s.get("name", "") for s in v2_sources if isinstance(s, dict)
                )
        return RetrievalResult(
            content=entry.get("content", ""),
            title=entry.get("title", ""),
            category=category,
            disaster_type=entry.get("disaster_type", "general"),
            score=score,
            source=sources or "internal",
            metadata=entry.get("metadata", {}),
        )

    def _semantic_search(
        self,
        query: str,
        disaster_type: Optional[str],
        category: Optional[str],
        top_k: int,
        *,
        phase: Optional[str] = None,
        topic: Optional[str] = None,
        disaster_types: Optional[List[str]] = None,
        include_general: bool = True,
    ) -> List[RetrievalResult]:
        try:
            q_emb = self.model.encode([query], convert_to_numpy=True)[0]
            sims = np.dot(self.embeddings, q_emb) / (
                np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_emb)
            )
            indices = self._filter_indices(
                disaster_type,
                category,
                phase=phase,
                topic=topic,
                disaster_types=disaster_types,
                include_general=include_general,
            )
            if not indices:
                indices = list(range(len(self.knowledge_base)))
            ranked = sorted(
                ((i, float(sims[i])) for i in indices), key=lambda x: x[1], reverse=True
            )
            results = []
            for idx, score in ranked[:top_k]:
                if score >= self.score_threshold:
                    results.append(self._result_from_entry(self.knowledge_base[idx], score))
            return results
        except Exception as e:
            logger.error(f"Semantic search failed: {e} - falling back")
            return self._tfidf_search(
                query,
                disaster_type,
                category,
                top_k,
                phase=phase,
                topic=topic,
                disaster_types=disaster_types,
                include_general=include_general,
            )

    def _tfidf_search(
        self,
        query: str,
        disaster_type: Optional[str],
        category: Optional[str],
        top_k: int,
        *,
        phase: Optional[str] = None,
        topic: Optional[str] = None,
        disaster_types: Optional[List[str]] = None,
        include_general: bool = True,
    ) -> List[RetrievalResult]:
        try:
            q_vec = self._tfidf.transform([query])
            sims = cosine_similarity(q_vec, self._tfidf_matrix)[0]
            indices = self._filter_indices(
                disaster_type,
                category,
                phase=phase,
                topic=topic,
                disaster_types=disaster_types,
                include_general=include_general,
            )
            if not indices:
                indices = list(range(len(self.knowledge_base)))
            ranked = sorted(
                ((i, float(sims[i])) for i in indices),
                key=lambda x: x[1],
                reverse=True,
            )
            results = []
            for idx, score in ranked[:top_k]:
                if score >= self.score_threshold:
                    results.append(self._result_from_entry(self.knowledge_base[idx], score))
            return results
        except Exception as e:
            logger.error(f"TF-IDF search failed: {e} - falling back to keyword")
            return self._keyword_search(
                query,
                disaster_type,
                category,
                top_k,
                phase=phase,
                topic=topic,
                disaster_types=disaster_types,
                include_general=include_general,
            )

    def _keyword_search(
        self,
        query: str,
        disaster_type: Optional[str],
        category: Optional[str],
        top_k: int,
        *,
        phase: Optional[str] = None,
        topic: Optional[str] = None,
        disaster_types: Optional[List[str]] = None,
        include_general: bool = True,
    ) -> List[RetrievalResult]:
        """Last-resort: simple set-overlap on words. No deps."""
        q_words = set(query.lower().split())
        indices = self._filter_indices(
            disaster_type,
            category,
            phase=phase,
            topic=topic,
            disaster_types=disaster_types,
            include_general=include_general,
        )
        results: List[RetrievalResult] = []
        for i in indices:
            entry = self.knowledge_base[i]
            words = set(self._searchable(entry).lower().split())
            overlap = len(q_words & words)
            if overlap > 0:
                score = overlap / max(len(q_words), 1)
                results.append(self._result_from_entry(entry, min(score, 1.0)))
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def get_guidance_by_disaster(
        self, disaster_type: str, phase: str = "during"
    ) -> Optional[Dict]:
        """Find an entry by (disaster_type, phase). v2 entries store the
        phase under ``phase``; v1 entries stored it under ``category`` —
        check both."""
        def _phase_of(e: Dict) -> Optional[str]:
            return e.get("phase") or e.get("category")

        for e in self.knowledge_base:
            if e.get("disaster_type") == disaster_type and _phase_of(e) == phase:
                return e
        for e in self.knowledge_base:
            if e.get("disaster_type") == "general" and _phase_of(e) == phase:
                return e
        return None

    def _builtin_minimal(self) -> List[Dict]:
        """Tiny fallback if data/knowledge_base.json is missing entirely."""
        return [
            {
                "id": "earthquake_during_min",
                "disaster_type": "earthquake",
                "category": "during",
                "title": "Earthquake — During Shaking",
                "content": "DROP, COVER, HOLD ON. Stay indoors away from windows. Call 1122 or 115.",
                "searchable_text": "earthquake quake shaking drop cover hold",
                "source": "NDMA",
                "metadata": {},
            },
            {
                "id": "flood_during_min",
                "disaster_type": "flood",
                "category": "during",
                "title": "Flood — During",
                "content": "Move to higher ground. Never walk or drive through flood water. Call 1122 / 115 / NDMA 051-9205037.",
                "searchable_text": "flood water rising higher ground evacuation",
                "source": "NDMA",
                "metadata": {},
            },
        ]


# ─── Singleton ────────────────────────────────────────────────────────────────
_retriever_instance: Optional[KnowledgeRetriever] = None


def get_knowledge_retriever(
    model_name: str = "all-MiniLM-L6-v2",
    score_threshold: float = 0.15,
    use_embeddings: bool = False,
) -> KnowledgeRetriever:
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = KnowledgeRetriever(
            model_name=model_name,
            score_threshold=score_threshold,
            use_embeddings=use_embeddings,
        )
    return _retriever_instance
