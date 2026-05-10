"""
JSON-schema declarations for the LLM tool-call layer.

Both Gemini (`google.generativeai`) and Groq's OpenAI-compatible API accept
function/tool declarations in JSON-schema form. We define the canonical
shape here once and adapt to provider-specific wrappers in llm_service.py.

Convention:
- Every tool returns a dict ``{"status": "ok"|"not_found"|"error", "data":
  {...}}``. The LLM is told (in the system prompt) to paraphrase data fields
  and never to invent beyond them.
- All parameters are strings or null. We avoid enum-typed params at the
  schema level because the KB / helplines vocab evolves; the executor
  validates / normalises instead.
"""
from __future__ import annotations


GET_HELPLINES = {
    "name": "get_helplines",
    "description": (
        "Return verified Pakistani helplines for a given province and category. "
        "Use this for ANY phone number — never type a number you didn't get "
        "from this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "province": {
                "type": "string",
                "description": (
                    "Pakistani province code: punjab, sindh, kpk, balochistan, "
                    "gilgit_baltistan, ajk, islamabad. Null for nationwide."
                ),
            },
            "category": {
                "type": "string",
                "description": (
                    "One of: emergency, medical, fire, police, gas, disaster, "
                    "weather, flood, women_safety, child_safety, mental_health. "
                    "Null for any."
                ),
            },
        },
        "required": [],
    },
}

GET_FIRST_AID_STEPS = {
    "name": "get_first_aid_steps",
    "description": (
        "Return canonical first-aid steps for a specific injury or condition. "
        "Use for first-aid / medical queries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "injury_type": {
                "type": "string",
                "description": (
                    "Injury / condition keyword: bleeding, cpr, burns, "
                    "snake_bite, electric_shock, drowning, heat_stroke, "
                    "choking, fracture, hypothermia, diabetic, seizure, "
                    "anaphylaxis, wound_infection."
                ),
            }
        },
        "required": ["injury_type"],
    },
}

GET_EVACUATION_INFO = {
    "name": "get_evacuation_info",
    "description": (
        "Return evacuation / shelter guidance for a city + disaster type. "
        "If the KB has no specific entry, returns generic guidance."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "Pakistani city name. Null for province-only guidance.",
            },
            "disaster_type": {
                "type": "string",
                "description": (
                    "earthquake, flood, heatwave, cyclone, fire, gas_leak, "
                    "building_collapse, electric_shock, or general."
                ),
            },
        },
        "required": ["disaster_type"],
    },
}

GET_QUICK_TIP = {
    "name": "get_quick_tip",
    "description": (
        "Return the short canonical safety-tip card for a given disaster type."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "disaster_type": {
                "type": "string",
                "description": (
                    "earthquake, flood, heatwave, cyclone, fire, gas_leak, "
                    "building_collapse, electric_shock, snake_bite, pandemic, "
                    "tsunami."
                ),
            }
        },
        "required": ["disaster_type"],
    },
}

ALL_TOOLS = [GET_HELPLINES, GET_FIRST_AID_STEPS, GET_EVACUATION_INFO, GET_QUICK_TIP]


def tool_names() -> list[str]:
    return [t["name"] for t in ALL_TOOLS]
