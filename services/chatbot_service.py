"""
Core Chatbot Service — orchestrates the NLP pipeline and response generation.
Pakistan-first; province-aware; province routing for helplines.
"""
import json
import os
import random
import uuid
from typing import Dict, List, Optional, Tuple
import logging

from config import (
    get_settings,
    IntentTypes,
    DisasterTypes,
    EMERGENCY_RESPONSE_TEMPLATE,
    FIRST_AID_DISCLAIMER,
)
from models import (
    ChatRequest,
    ChatResponse,
    IntentResult,
    EntityResult,
    HelplineInfo,
    SourceCitation,
    UrgencyLevel,
)
from nlp import (
    get_preprocessor,
    get_intent_classifier,
    get_entity_extractor,
    get_knowledge_retriever,
)


# ─── Crisis routing (locked Phase 3 decision O10) ─────────────────────────────
# Hand-curated phrase list. False positives route to crisis resources (low
# harm — user gets the helplines and the canonical reassurance copy); false
# negatives route to the LLM (high harm — LLM may improvise on suicidal
# ideation). So this list is intentionally BROAD.
#
# Drafted by Claude Code. **Project owner review required before merge** per
# locked decision.
CRISIS_PHRASES = (
    # Direct
    "kill myself",
    "i want to die",
    "i wanna die",
    "i am going to die",
    "going to kill myself",
    "going to end it",
    "going to end my life",
    "end my life",
    "ending my life",
    "take my own life",
    "taking my own life",
    "suicide",
    "suicidal",
    # Indirect / cessation
    "no reason to live",
    "no point in living",
    "nothing to live for",
    "don't want to live",
    "do not want to live",
    "want it to end",
    "want this to end",
    "i cant go on",
    "i can't go on",
    "i cannot go on",
    "i can not go on",
    "tired of living",
    "tired of being alive",
    # Plan / method indicators (case-insensitive substring match)
    "hang myself",
    "hanging myself",
    "shoot myself",
    "shooting myself",
    "overdose myself",
    "jump off",
    "jumping off",
    "cut myself badly",
    "slit my wrists",
    # Self-harm signals
    "harm myself",
    "hurt myself",
    "cutting myself",
    "self-harm",
    "self harm",
    # Goodbye / bequest signals
    "goodbye world",
    "this is my last",
    "won't be here tomorrow",
    "wont be here tomorrow",
    "won't be around",
)


def _is_crisis(text: str) -> bool:
    """Substring scan against the curated CRISIS_PHRASES list. Lowercased
    on both sides."""
    low = text.lower()
    return any(phr in low for phr in CRISIS_PHRASES)


CRISIS_TEMPLATE = """🆘 **Help is available — you don't have to face this alone.**

If you are in immediate danger, **call 115 (Edhi)** right now. Tell them you need urgent help.

Free counselling support in Pakistan:

- **Umang** — 0311-7786264 (24/7 mental-health helpline, GCP-certified clinical psychologists)
- **Rozan Counseling** — 0304-111-1741 (psychosocial support, depression, trauma)

If you can, please:
1. Call one of the numbers above, or 115.
2. Reach out to one trusted person right now — a family member, friend, neighbour.
3. Move away from anything that could hurt you.

You matter. Talking to someone trained makes a real difference. Stay on the line until help arrives."""

logger = logging.getLogger(__name__)
settings = get_settings()


class ChatbotService:
    """Main chatbot service that orchestrates the NLP pipeline."""

    REGION_ALIASES = {
        "default": "pakistan",
        "pk": "pakistan",
        "pakistani": "pakistan",
        "pakistan": "pakistan",
    }

    def __init__(self):
        self.preprocessor = get_preprocessor(anonymize_pii=settings.ANONYMIZE_LOGS)
        self.intent_classifier = get_intent_classifier()
        self.entity_extractor = get_entity_extractor(use_spacy=settings.USE_SPACY)
        self.knowledge_retriever = get_knowledge_retriever(
            model_name=settings.SENTENCE_TRANSFORMER_MODEL,
            score_threshold=settings.RETRIEVAL_SCORE_THRESHOLD,
            use_embeddings=settings.USE_EMBEDDINGS,
        )

        self.templates = self._load_templates()
        self.helplines_data = self._load_helplines()

        self.emergency_keywords = set(
            kw.strip().lower()
            for kw in settings.EMERGENCY_KEYWORDS.split(",")
            if kw.strip()
        )

    # ─── Data loading ─────────────────────────────────────────────────────────
    def _load_templates(self) -> Dict:
        path = os.path.join(
            os.path.dirname(__file__), "..", "data", "response_templates.json"
        )
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load templates: {e}")
        return {
            "greetings": {"default": "Hello! I'm here to help with disaster safety information."},
            "farewell": {"default": "Stay safe!"},
            "gratitude": {"default": "You're welcome!"},
            "fallback": {"default": "I can help with disaster safety, helplines, and first aid."},
        }

    def _load_helplines(self) -> Dict:
        path = os.path.join(
            os.path.dirname(__file__), "..", "data", "helplines.json"
        )
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load helplines: {e}")
        return {
            "regions": {
                "pakistan": {
                    "country": "Pakistan",
                    "emergency_number": "1122",
                    "helplines": [
                        {
                            "name": "Rescue 1122",
                            "number": "1122",
                            "description": "Emergency Rescue",
                            "available_24x7": True,
                            "category": "emergency",
                        }
                    ],
                    "provinces": {},
                }
            },
            "aliases": {"default": "pakistan"},
            "category_priorities": {},
        }

    # ─── Region helpers ───────────────────────────────────────────────────────
    def _normalize_region(self, region: Optional[str]) -> str:
        r = (region or settings.DEFAULT_REGION or "pakistan").strip().lower()
        # Try aliases from helplines.json first, then static map
        aliases = self.helplines_data.get("aliases", {})
        if r in aliases:
            return aliases[r]
        if r in self.REGION_ALIASES:
            return self.REGION_ALIASES[r]
        return r

    def _region_data(self, region: str) -> Dict:
        regions = self.helplines_data.get("regions", {})
        return regions.get(region, regions.get("pakistan", {}))

    def _resolve_province(
        self, request: ChatRequest, processed_text: str
    ) -> Optional[str]:
        if request.province:
            return request.province.lower().replace("-", "_").replace(" ", "_")
        return self.entity_extractor.extract_province(
            processed_text, city_hint=request.city
        )

    # ─── Intents that stay on the legacy template path even when USE_LLM=true ─
    # These intents already route to a careful, hand-authored template that
    # includes verified helplines and the right disclaimers. LLM creativity
    # here is high-risk for low gain.
    TEMPLATE_ONLY_INTENTS = frozenset(
        {
            IntentTypes.GREETINGS,
            IntentTypes.FAREWELL,
            IntentTypes.GRATITUDE,
            IntentTypes.WEATHER_INFO,
            IntentTypes.DONATION_VOLUNTEERING,
            IntentTypes.MENTAL_HEALTH,  # mental-health template is sensitive — keep deterministic
            IntentTypes.REPORT_INCIDENT,
            IntentTypes.HELPLINE_QUERY,  # we already curate helpline rendering
        }
    )

    # ─── Public entrypoint ────────────────────────────────────────────────────
    async def process_message(self, request: ChatRequest) -> ChatResponse:
        message_id = uuid.uuid4().hex[:12]
        region = self._normalize_region(request.region)

        try:
            # 1. Preprocess
            processed_text, _meta = self.preprocessor.preprocess(request.message)
            if not processed_text:
                return self._fallback_response(
                    message_id,
                    "I couldn't understand that message. Could you please rephrase?",
                    region,
                )

            # 2. Province (used for helpline routing)
            province = self._resolve_province(request, processed_text)

            # 3a. CRISIS fast-path (Phase 3 — locked O10). Suicide / self-harm
            # phrasings are routed to the hand-written crisis template. NEVER
            # to the LLM. The template carries the canonical 115 + Umang +
            # Rozan numbers. False positives are an acceptable cost.
            if _is_crisis(request.message) or _is_crisis(processed_text):
                return self._build_crisis_response(message_id, region, province)

            # 3b. Emergency fast path (deterministic, NO LLM).
            is_emergency, _score = self._check_emergency(processed_text)
            if is_emergency:
                return await self._handle_emergency(
                    message_id, processed_text, region, province, request
                )

            # 4. Classify intent
            intent_result = self.intent_classifier.classify(processed_text)

            # 5. Extract entities
            entities = self.entity_extractor.extract(
                processed_text, disaster_context=intent_result.sub_intent
            )

            # 6a. LLM path (Phase 3) — PRIMARY response path when USE_LLM=true
            # and the intent isn't deliberately kept on the template path.
            #
            # Phase 5a.1 contract (locked, regression-tested in
            # test_llm_primary_path.py):
            #
            #   - SAFETY_ADVICE and FIRST_AID always go through here when
            #     USE_LLM=true, including bare-noun queries like "flood" /
            #     "earthquake" / "first aid for burns".
            #   - Retrieval might return weak / empty passages for very
            #     short queries — we still call the LLM; the system prompt
            #     instructs the model to say "I don't have verified info"
            #     when SOURCES is empty rather than hallucinate.
            #   - Legacy `_route_intent` is the safety net ONLY when this
            #     path returns None (LLMUnavailable, both providers down)
            #     or raises. The legacy KB-chunk template is no longer the
            #     default response shape for safety_advice / first_aid.
            if (
                settings.USE_LLM
                and intent_result.intent not in self.TEMPLATE_ONLY_INTENTS
            ):
                try:
                    llm_response = await self._route_intent_via_llm(
                        message_id=message_id,
                        text=processed_text,
                        original_message=request.message,
                        session_id=request.session_id,
                        intent=intent_result,
                        entities=entities,
                        request=request,
                        region=region,
                        province=province,
                    )
                    if llm_response is not None:
                        return llm_response
                except Exception as e:
                    logger.warning(
                        "LLM path failed (%s); falling back to legacy template", e
                    )
                    # Fall through to legacy.

            # 6b. Legacy template path (safety net — Phase 1 + 2 behaviour
            # unchanged). Reached when USE_LLM=false (kill switch) OR the
            # LLM path returned None (both providers unavailable).
            return await self._route_intent(
                message_id,
                processed_text,
                intent_result,
                entities,
                request,
                region=region,
                province=province,
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return self._fallback_response(
                message_id,
                "I encountered an error processing your request. For emergencies, please call 115 or 1122.",
                region,
            )

    # ─── Emergency detection ──────────────────────────────────────────────────
    def _check_emergency(self, text: str) -> Tuple[bool, float]:
        """
        Phase 1 over-fire fix (audit B4): every standalone trigger requires a
        disaster/injury anchor. Bare 'help'/'emergency'/'sos' no longer fire
        on their own — they need to co-occur with something that names the
        threat. The urgency_score path (>= 0.6) is preserved as the safety
        net for distress phrasings like "im scared please".
        """
        t = text.lower()

        # 1) Hard-coded phrases — each one is unambiguous, anchored on a
        # disaster/injury word. "help me" alone removed; replaced by anchored
        # variants. "emergency" / "sos" alone removed for the same reason.
        emergency_phrases = [
            "i'm trapped", "im trapped", "i am trapped",
            "someone is dying", "people are dying",
            "there's a fire", "there is a fire", "fire now",
            "earthquake happening", "earthquake now",
            "flood rising", "water rising fast", "flood now",
            "gas leak now", "gas is leaking", "smell gas now",
            "building collapsed", "wall collapsed", "roof collapsed",
            "heart attack", "having a stroke",
            "i want to kill myself", "kill myself",
            "help me i'm hurt", "help me im hurt", "help me i am hurt",
            "help me i'm trapped", "help me im trapped",
            "help me i'm bleeding", "help me im bleeding",
            "help me drowning", "help me i'm drowning",
            # Anchored bleeding phrases — the keyword-set rule alone catches
            # "bleeding" but only at urgency >= 0.6, so phrasings like
            # "i'm bleeding badly please help immediately" land at 0.5 and
            # would otherwise miss. These are unambiguously emergencies.
            "i'm bleeding", "im bleeding", "bleeding badly",
            "bleeding heavily", "bleeding a lot", "won't stop bleeding",
        ]
        for phr in emergency_phrases:
            if phr in t:
                return True, 0.95

        # 2) Keyword-set overlap: was ">= 2 keywords"; now requires
        # urgency_score >= 0.6 AND >= 1 keyword (locked Phase 1 decision).
        # Bare 'help'/'emergency' have already been removed from the keyword
        # set in config.EMERGENCY_KEYWORDS, so a single keyword now genuinely
        # signals threat (trapped, drowning, bleeding, etc.).
        urgency = self.preprocessor.extract_urgency_signals(text)
        words = set(t.split())
        keyword_hit = len(words & self.emergency_keywords) >= 1
        if keyword_hit and urgency["urgency_score"] >= 0.6:
            return True, max(0.85, urgency["urgency_score"])

        # 3) Pure urgency score safety net — even with no keywords, very
        # high distress signals route to emergency. Tuned to 0.6 threshold
        # consistent with the keyword path.
        if urgency["urgency_score"] >= 0.6:
            return True, urgency["urgency_score"]

        return False, 0.0

    # ─── Crisis fast-path (Phase 3, never calls LLM) ──────────────────────────
    def _build_crisis_response(
        self, message_id: str, region: str, province: Optional[str]
    ) -> ChatResponse:
        # Surface the crisis-specific helplines: Umang (24/7) + Rozan + 115.
        helplines: List[HelplineInfo] = []
        for entry in self._region_data(region).get("helplines", []) or []:
            cat = entry.get("category", "")
            num = entry.get("number", "")
            if cat == "mental_health" or num in {"115"}:
                helplines.append(
                    HelplineInfo(
                        name=entry.get("name", ""),
                        number=num,
                        description=entry.get("description", ""),
                        available_24x7=entry.get("available_24x7", True),
                        region=region,
                    )
                )
        # Cap at 4 — keep the message scannable in a panic state.
        helplines = helplines[:4]
        return ChatResponse(
            message_id=message_id,
            response=CRISIS_TEMPLATE,
            response_type="crisis",
            intent=IntentResult(
                intent=IntentTypes.MENTAL_HEALTH,
                confidence=0.99,
                sub_intent="self_harm",
            ),
            entities=[],
            helplines=helplines,
            urgency_level=UrgencyLevel.CRITICAL,
            suggested_actions=[
                "Call Umang 0311-7786264",
                "Call 115 (Edhi) now",
                "Reach out to one trusted person",
            ],
            related_topics=[],
            confidence_score=0.99,
            is_emergency=True,
            offline_available=True,
            region=region,
            province=province,
            sources=[],
            used_llm=False,
        )

    # ─── LLM path (Phase 3, USE_LLM=true) ─────────────────────────────────────
    async def _route_intent_via_llm(
        self,
        *,
        message_id: str,
        text: str,
        original_message: str,
        session_id: Optional[str],
        intent,
        entities: List,
        request: ChatRequest,
        region: str,
        province: Optional[str],
    ) -> Optional[ChatResponse]:
        """
        Layer 3 (RAG) → Layer 4 (LLM) → Layer 5 (validator). Returns None
        if it can't run (key missing, both providers down) — caller falls
        through to the legacy template path.
        """
        # Lazy imports — keep USE_LLM=false deploys lightweight.
        from services.llm_service import (
            LLMUnavailable,
            ChatTurn as LLMChatTurn,
            format_sources_block,
            get_llm_service,
        )
        from services.session_store import get_session_store
        from services.output_validator import get_output_validator

        # Layer 3 — RAG. Use disaster_type when known to bias retrieval.
        disaster_type = intent.sub_intent or self._detect_disaster_from_entities(entities)
        # Lower the score floor for the LLM grounding pass so weak matches
        # still feed the prompt (the LLM, with the system rule "base every
        # safety claim on SOURCES", can still produce a useful answer).
        # Without this, short queries like "heatwave in karachi" land at
        # ~0.13 and the LLM falls back to training-data hallucination.
        saved_threshold = self.knowledge_retriever.score_threshold
        try:
            self.knowledge_retriever.score_threshold = 0.05
            passages = self.knowledge_retriever.retrieve(
                text,
                disaster_type=disaster_type,
                top_k=settings.TOP_K_RESULTS,
            )
            # If the disaster-filtered pass returned nothing, retry without
            # the disaster filter so we still surface SOMETHING relevant.
            if not passages and disaster_type:
                passages = self.knowledge_retriever.retrieve(
                    text, top_k=settings.TOP_K_RESULTS,
                )
        finally:
            self.knowledge_retriever.score_threshold = saved_threshold

        sources_block = format_sources_block(passages)

        # Layer 4 — LLM (with tool-call loop).
        store = get_session_store()
        history_turns = store.get(session_id or "", max_turns=settings.SESSION_MAX_TURNS)
        llm_history = [LLMChatTurn(role=t.role, content=t.content) for t in history_turns]

        try:
            llm_resp = await get_llm_service().generate(
                user_message=original_message,
                history=llm_history,
                sources_block=sources_block,
                province=province,
                intent=intent.intent,
            )
        except LLMUnavailable:
            return None
        if not (llm_resp and llm_resp.text):
            return None

        # Layer 5 — Validator.
        validator = get_output_validator(self)
        validated = validator.validate(llm_resp.text, intent=intent.intent)

        # Persist conversation history (post-validation, post-truncation —
        # what the user actually saw).
        if session_id:
            store.append(session_id, "user", original_message)
            store.append(session_id, "assistant", validated.text)

        # Source citations surfaced to the client (deduped by name).
        source_citations: List[SourceCitation] = []
        seen_names: set = set()
        for p in passages:
            if not p.source:
                continue
            for name in str(p.source).split(";"):
                name = name.strip()
                if name and name not in seen_names:
                    seen_names.add(name)
                    source_citations.append(SourceCitation(name=name, url=None))

        return ChatResponse(
            message_id=message_id,
            response=validated.text,
            response_type="safety_advice_llm",
            intent=IntentResult(
                intent=intent.intent,
                confidence=intent.confidence,
                sub_intent=disaster_type,
            ),
            entities=self._convert_entities(entities),
            helplines=self._get_helplines(region, province=province, limit=3),
            urgency_level=UrgencyLevel.MEDIUM,
            suggested_actions=self._suggestions_for_disaster(disaster_type),
            related_topics=[p.title for p in passages[:3]],
            confidence_score=max(intent.confidence, 0.7),
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
            sources=source_citations[:5],
            used_llm=True,
        )

    async def _handle_emergency(
        self,
        message_id: str,
        text: str,
        region: str,
        province: Optional[str],
        request: ChatRequest,
    ) -> ChatResponse:
        region_data = self._region_data(region)
        emergency_number = region_data.get("emergency_number", "1122")

        disaster_type = self.entity_extractor.detect_disaster_type(text)

        specific_guidance = ""
        if disaster_type:
            results = self.knowledge_retriever.retrieve(
                text, disaster_type=disaster_type, phase="during", top_k=1
            )
            if results:
                # Trim to keep the message scannable in a panic
                specific_guidance = results[0].content[:600]

        helplines = self._get_helplines(
            region,
            province=province,
            categories=["emergency", "disaster", "medical"],
            limit=5,
        )
        helplines_text = self._format_helplines_text(helplines)

        response_text = (
            self.templates.get("emergency_detected", {}).get("default")
            or EMERGENCY_RESPONSE_TEMPLATE
        ).format(
            emergency_number=emergency_number,
            specific_guidance=specific_guidance
            or "Stay calm and follow emergency responder instructions.",
            helplines=helplines_text,
        )

        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="emergency",
            intent=IntentResult(
                intent=IntentTypes.EMERGENCY,
                confidence=0.95,
                sub_intent=disaster_type,
            ),
            entities=[],
            helplines=helplines,
            urgency_level=UrgencyLevel.CRITICAL,
            suggested_actions=[
                f"Call {emergency_number} immediately",
                "Move to safety if possible",
                "Help others if safe to do so",
            ],
            related_topics=[],
            confidence_score=0.95,
            is_emergency=True,
            offline_available=True,
            region=region,
            province=province,
        )

    # ─── Routing ──────────────────────────────────────────────────────────────
    async def _route_intent(
        self,
        message_id: str,
        text: str,
        intent,
        entities: List,
        request: ChatRequest,
        region: str,
        province: Optional[str],
    ) -> ChatResponse:
        handlers = {
            IntentTypes.GREETINGS: self._handle_greeting,
            IntentTypes.FAREWELL: self._handle_farewell,
            IntentTypes.GRATITUDE: self._handle_gratitude,
            IntentTypes.SAFETY_ADVICE: self._handle_safety_advice,
            IntentTypes.HELPLINE_QUERY: self._handle_helpline_query,
            IntentTypes.SHELTER_INFO: self._handle_shelter_info,
            IntentTypes.EVACUATION_ROUTE: self._handle_evacuation_route,
            IntentTypes.FIRST_AID: self._handle_first_aid,
            IntentTypes.WEATHER_INFO: self._handle_weather_info,
            IntentTypes.REPORT_INCIDENT: self._handle_report_incident,
            IntentTypes.DONATION_VOLUNTEERING: self._handle_donation,
            IntentTypes.MENTAL_HEALTH: self._handle_mental_health,
            IntentTypes.FALLBACK: self._handle_fallback,
        }
        handler = handlers.get(intent.intent, self._handle_fallback)
        return await handler(
            message_id, text, intent, entities, request,
            region=region, province=province,
        )

    # ─── Handlers ─────────────────────────────────────────────────────────────
    async def _handle_greeting(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("greetings", {})
        response_text = templates.get(
            "default", "Hello! How can I help you with disaster safety in Pakistan?"
        )
        variants = templates.get("variants", [])
        if variants and random.random() > 0.7:
            response_text = random.choice(variants)

        suggestions = self.templates.get("suggestions", {}).get("general", [])
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="greeting",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=[],
            helplines=[],
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=suggestions[:4],
            related_topics=["Earthquake safety", "Flood preparedness", "Heatwave safety"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_farewell(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("farewell", {})
        response_text = templates.get(
            "default", "Stay safe! Don't hesitate to return if you need help."
        )
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="farewell",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=[],
            helplines=[],
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=[],
            related_topics=[],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_gratitude(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("gratitude", {})
        response_text = templates.get("default", "You're welcome! Stay safe.")
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="gratitude",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=[],
            helplines=[],
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=[
                "Ask about another disaster type",
                "Get emergency helplines",
            ],
            related_topics=[],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    # Phase 5a Fix 3 (extended): same lowered floor logic as
    # _handle_first_aid. Bare 1-word disaster queries like "flood",
    # "earthquake", "fire" score in the 0.05-0.13 range against TF-IDF
    # because cosine similarity is diluted by the entries' richer term sets.
    # Without this floor lower the legacy template path falls through to the
    # fallback handler even though the classifier correctly routed to
    # safety_advice + sub_intent.
    _SAFETY_ADVICE_SCORE_FLOOR = 0.05

    async def _handle_safety_advice(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        disaster_type = intent.sub_intent or self._detect_disaster_from_entities(entities)

        saved_threshold = self.knowledge_retriever.score_threshold
        try:
            # Drop the score floor for the retrieval call. When `disaster_type`
            # is set the classifier has already decided this is safety_advice
            # for that disaster — retrieval is just picking which entry to
            # surface, and the disaster_type filter has already pre-narrowed
            # the candidate set. Score is then a tie-breaker, not a gate.
            self.knowledge_retriever.score_threshold = 0.0
            results = self.knowledge_retriever.retrieve(
                text, disaster_type=disaster_type, top_k=settings.TOP_K_RESULTS
            )
        finally:
            self.knowledge_retriever.score_threshold = saved_threshold

        # If the classifier identified a disaster sub_intent, trust it and
        # surface the top-1 entry from the disaster-filtered retrieval —
        # even at score 0.0. Common-vocabulary terms like "fire" have very
        # low TF-IDF IDF (they appear in many entries' searchable_text) so
        # the cosine similarity collapses to ~0 even when the entry IS
        # exactly the right one.
        # When NO sub_intent was set (open-ended query), the score floor
        # still gates surfacing — otherwise unrelated content would leak.
        score_ok = (
            results
            and (
                disaster_type is not None
                or results[0].score >= self._SAFETY_ADVICE_SCORE_FLOOR
            )
        )
        if score_ok:
            main = results[0]
            response_text = f"**{main.title}**\n\n{main.content}"

            helplines = self._get_helplines(region, province=province, limit=3)
            if helplines:
                response_text += (
                    f"\n\n**Emergency Contacts:**\n{self._format_helplines_text(helplines)}"
                )

            related = [r.title for r in results[1:3]] if len(results) > 1 else []

            return ChatResponse(
                message_id=message_id,
                response=response_text,
                response_type="safety_advice",
                intent=IntentResult(
                    intent=intent.intent,
                    confidence=intent.confidence,
                    sub_intent=disaster_type,
                ),
                entities=self._convert_entities(entities),
                helplines=helplines,
                urgency_level=UrgencyLevel.MEDIUM,
                suggested_actions=self._suggestions_for_disaster(disaster_type),
                related_topics=related,
                confidence_score=max(intent.confidence, results[0].score),
                is_emergency=False,
                offline_available=True,
                region=region,
                province=province,
            )
        # Low-confidence retrieval → fallback
        return await self._handle_fallback(
            message_id, text, intent, entities, request, region, province
        )

    async def _handle_helpline_query(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        # Detect a category if user asked specifically
        category = None
        t = text.lower()
        if "police" in t:
            category = "police"
        elif "fire" in t or "brigade" in t:
            category = "fire"
        elif "ambulance" in t or "medical" in t or "hospital" in t:
            category = "medical"
        elif "gas" in t:
            category = "gas"
        elif "child" in t:
            category = "child_safety"
        elif "women" in t:
            category = "women_safety"
        elif "mental" in t or "counseling" in t or "depression" in t:
            category = "mental_health"
        elif "weather" in t or "forecast" in t:
            category = "weather"
        elif "flood" in t:
            category = "flood"
        elif "disaster" in t or "earthquake" in t:
            category = "disaster"

        helplines = self._get_helplines(
            region,
            province=province,
            categories=[category] if category else None,
            limit=10,
        )

        header = "**Emergency Helplines"
        if province:
            header += f" — {province.replace('_', ' ').title()}"
        header += ":**"

        response_text = (
            f"{header}\n\n{self._format_helplines_text(helplines)}\n\n"
            f"💾 *Save these numbers for quick access during emergencies.*"
        )

        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="helplines",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=helplines,
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=[
                "Share these numbers with family",
                "Save to your phone",
            ],
            related_topics=["Disaster preparedness", "Emergency kit"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_shelter_info(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("shelter_info", {})
        response_text = templates.get(
            "generic",
            "Contact your district administration or PDMA for shelter information.",
        )
        helplines = self._get_helplines(
            region, province=province, categories=["disaster", "emergency"], limit=3
        )
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="shelter_info",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=helplines,
            urgency_level=UrgencyLevel.MEDIUM,
            suggested_actions=[
                "Contact local PDMA",
                "Listen to PTV / FM emergency broadcasts",
                "Follow official evacuation orders",
            ],
            related_topics=["Evacuation tips", "What to pack for evacuation"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_evacuation_route(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("evacuation_route", {})
        response_text = templates.get(
            "generic",
            "Move purposefully to higher ground (floods) or open area (earthquake). "
            "Take only essentials — CNIC, phone, cash, medications, water.",
        )
        helplines = self._get_helplines(
            region, province=province, categories=["disaster", "emergency"], limit=3
        )
        suggestions = (
            self.templates.get("suggestions", {}).get("evacuation")
            or [
                "What to pack for evacuation",
                "Where is the nearest shelter?",
                "Helpline for my province",
            ]
        )
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="evacuation_route",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=helplines,
            urgency_level=UrgencyLevel.MEDIUM,
            suggested_actions=suggestions[:4],
            related_topics=["Emergency kit", "Family communication plan"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    # First-aid retrieval pass uses a relaxed score floor — TF-IDF on
    # short queries like "burnt my hand" scores ~0.10–0.15, well below
    # the global RETRIEVAL_SCORE_THRESHOLD (0.15). Phase 5a Fix 3 mirrors
    # what Phase 3 did for LLM grounding: lower the floor for THIS handler
    # specifically so we surface a real KB entry instead of the generic
    # "specify the injury" fallback that was firing too aggressively
    # in production. Restored to the global threshold if/when retrieval
    # quality is tuned at the index level.
    _FIRST_AID_SCORE_FLOOR = 0.05

    async def _handle_first_aid(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        # Audit B11 (Phase 2): retrieve ONLY first-aid topic entries from the
        # general bucket. Without this, disaster-specific entries (e.g.
        # earthquake.during.outdoors.001) would dilute first-aid responses
        # and weaken Phase 3's LLM grounding for medical queries.
        #
        # Phase 5a Fix 3: temporarily lower the retriever's score_threshold
        # so verb-form queries like "burnt my hand on stove" actually surface
        # the burns entry. Without this the retriever's internal filter drops
        # everything below 0.15 BEFORE the results reach this handler, and
        # the generic "specify the injury" template fires for almost every
        # natural phrasing.
        saved_threshold = self.knowledge_retriever.score_threshold
        try:
            self.knowledge_retriever.score_threshold = self._FIRST_AID_SCORE_FLOOR
            results = self.knowledge_retriever.retrieve(
                text,
                topic="first_aid",
                disaster_types=["general"],
                include_general=False,
                top_k=2,
            )
        finally:
            self.knowledge_retriever.score_threshold = saved_threshold

        if results and results[0].score >= self._FIRST_AID_SCORE_FLOOR:
            response_text = f"{results[0].content}\n\n{FIRST_AID_DISCLAIMER}"
        else:
            response_text = (
                "**Basic First Aid Guidance**\n\n"
                "Please specify the type of injury or condition for detailed steps.\n\n"
                "**General Principles:**\n"
                "1. Ensure the scene is safe\n"
                "2. Call **115** or **1122** for serious injuries\n"
                "3. Don't move seriously injured people\n"
                "4. Apply basic first aid within your training\n\n"
                f"{FIRST_AID_DISCLAIMER}"
            )

        helplines = self._get_helplines(
            region, province=province, categories=["medical", "emergency"], limit=3
        )
        suggestions = self.templates.get("suggestions", {}).get(
            "first_aid",
            ["How to control bleeding", "Basic CPR steps", "First aid for burns"],
        )
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="first_aid",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=helplines,
            urgency_level=UrgencyLevel.MEDIUM,
            suggested_actions=suggestions[:4],
            related_topics=["CPR basics", "Burns treatment", "Bleeding control"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_weather_info(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("weather_info", {})
        response_text = templates.get(
            "generic",
            "I don't have real-time weather data. Check the Pakistan Meteorological Department: pmd.gov.pk",
        )
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="weather_info",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=[],
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=[
                "Check PMD website",
                "Sign up for NDMA / PDMA alerts",
            ],
            related_topics=["Cyclone preparedness", "Flood safety", "Heatwave safety"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_report_incident(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        region_data = self._region_data(region)
        emergency_number = region_data.get("emergency_number", "1122")

        templates = self.templates.get("report_incident", {})
        response_text = templates.get(
            "default",
            "To report an emergency, call {emergency_number}.",
        ).format(emergency_number=emergency_number)

        helplines = self._get_helplines(
            region,
            province=province,
            categories=["emergency", "disaster", "police"],
            limit=5,
        )

        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="report_incident",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=helplines,
            urgency_level=UrgencyLevel.HIGH,
            suggested_actions=[
                f"Call {emergency_number} for emergencies",
                "Provide your exact location",
                "Stay safe while reporting",
            ],
            related_topics=[],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_donation(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("donation_volunteering", {})
        response_text = templates.get("generic")

        if not response_text:
            # Fall back to KB if templates don't have it
            results = self.knowledge_retriever.retrieve(
                "donate volunteer", phase="general", top_k=1
            )
            response_text = (
                results[0].content
                if results
                else "Trusted Pakistani relief NGOs include Edhi, Chhipa, JDC, Saylani, Al-Khidmat, Pakistan Red Crescent."
            )

        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="donation_volunteering",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=[],
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=[
                "Edhi Foundation",
                "Pakistan Red Crescent",
                "Blood donation centers",
            ],
            related_topics=["How to volunteer safely", "Zakat for relief"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_mental_health(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("mental_health", {})
        response_text = templates.get("generic")

        if not response_text:
            # Phase 2: prefer the dedicated mental_health bucket (5 entries
            # added). Fall back to the carry-over general entry if needed.
            results = self.knowledge_retriever.retrieve(
                "mental health post disaster anxiety counseling",
                disaster_types=["mental_health"],
                include_general=True,
                top_k=1,
            )
            response_text = (
                results[0].content
                if results
                else "Free mental health support: Rozan 0304-1111741, Umang 0311-7786264. If in crisis, call 115."
            )

        # Mental-health helplines have category 'mental_health'
        helplines = self._get_helplines(
            region, province=province, categories=["mental_health", "medical"], limit=4
        )
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="mental_health",
            intent=IntentResult(intent=intent.intent, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=helplines,
            urgency_level=UrgencyLevel.MEDIUM,
            suggested_actions=[
                "Talk to family or trusted friends",
                "Limit news exposure",
                "Try Rozan or Umang counseling line",
            ],
            related_topics=["Children's reactions to disaster", "Self-care basics"],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    async def _handle_fallback(
        self, message_id, text, intent, entities, request, region, province
    ) -> ChatResponse:
        templates = self.templates.get("fallback", {})
        if intent.confidence < 0.4:
            response_text = templates.get(
                "low_confidence", templates.get("default", "")
            )
        else:
            response_text = templates.get(
                "default",
                "I'm not sure about that. I can help with disaster safety, "
                "Pakistan emergency helplines, and first aid information.",
            )
        helplines = self._get_helplines(
            region, province=province, categories=["emergency"], limit=2
        )
        suggestions = self.templates.get("suggestions", {}).get("general", [])
        return ChatResponse(
            message_id=message_id,
            response=response_text,
            response_type="fallback",
            intent=IntentResult(intent=IntentTypes.FALLBACK, confidence=intent.confidence),
            entities=self._convert_entities(entities),
            helplines=helplines,
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=suggestions[:4],
            related_topics=[
                "Earthquake safety",
                "Flood safety",
                "Heatwave safety",
                "Pakistan emergency numbers",
            ],
            confidence_score=intent.confidence,
            is_emergency=False,
            offline_available=True,
            region=region,
            province=province,
        )

    def _fallback_response(
        self, message_id: str, message: str, region: str
    ) -> ChatResponse:
        helplines = self._get_helplines(region, categories=["emergency"], limit=2)
        return ChatResponse(
            message_id=message_id,
            response=message,
            response_type="fallback",
            intent=IntentResult(intent=IntentTypes.FALLBACK, confidence=0.0),
            entities=[],
            helplines=helplines,
            urgency_level=UrgencyLevel.LOW,
            suggested_actions=["Try rephrasing your question"],
            related_topics=[],
            confidence_score=0.0,
            is_emergency=False,
            offline_available=True,
            region=region,
        )

    # ─── Helpline assembly (province-aware) ───────────────────────────────────
    def _get_helplines(
        self,
        region: str,
        province: Optional[str] = None,
        categories: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[HelplineInfo]:
        region = self._normalize_region(region)
        region_data = self._region_data(region)

        all_helplines: List[Dict] = list(region_data.get("helplines", []) or [])

        # Inject the relevant province PDMA at the top if applicable
        provinces = region_data.get("provinces", {}) or {}
        if province and province in provinces:
            pdma = provinces[province].get("pdma")
            if pdma:
                # avoid duplicate insert if already in list
                if not any(
                    h.get("number") == pdma.get("number") for h in all_helplines
                ):
                    all_helplines.insert(0, {**pdma, "available_24x7": True})

        if categories:
            filtered = [h for h in all_helplines if h.get("category") in categories]
            if not filtered:
                filtered = all_helplines
        else:
            filtered = all_helplines

        priorities = self.helplines_data.get("category_priorities", {}) or {}
        filtered.sort(key=lambda h: priorities.get(h.get("category", ""), 99))

        out: List[HelplineInfo] = []
        for h in filtered[:limit]:
            out.append(
                HelplineInfo(
                    name=h.get("name", ""),
                    number=h.get("number", ""),
                    description=h.get("description", ""),
                    available_24x7=h.get("available_24x7", True),
                    region=region,
                )
            )
        return out

    def _format_helplines_text(self, helplines: List[HelplineInfo]) -> str:
        lines = []
        for h in helplines:
            tag = "24/7" if h.available_24x7 else "Limited hours"
            lines.append(f"- **{h.name}:** {h.number} ({tag})")
        return "\n".join(lines)

    def _convert_entities(self, entities: List) -> List[EntityResult]:
        return [
            EntityResult(
                entity_type=e.entity_type,
                value=e.value,
                confidence=e.confidence,
                start=e.start,
                end=e.end,
            )
            for e in entities[:10]
        ]

    def _detect_disaster_from_entities(self, entities: List) -> Optional[str]:
        for e in entities:
            if e.entity_type == "disaster":
                return e.normalized_value
        return None

    def _suggestions_for_disaster(
        self, disaster_type: Optional[str]
    ) -> List[str]:
        base = self.templates.get("suggestions", {}).get(
            "after_safety_advice",
            [
                "Emergency helplines for my province",
                "How to prepare an emergency kit",
                "First aid basics",
            ],
        )
        if not disaster_type:
            return [s.replace("{disaster_type}", "this disaster") for s in base][:4]
        return [s.replace("{disaster_type}", disaster_type) for s in base][:4]


# ─── Singleton ────────────────────────────────────────────────────────────────
_chatbot_service: Optional[ChatbotService] = None


def get_chatbot_service() -> ChatbotService:
    global _chatbot_service
    if _chatbot_service is None:
        _chatbot_service = ChatbotService()
    return _chatbot_service
