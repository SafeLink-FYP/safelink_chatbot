#!/usr/bin/env python
"""
Phase 2 KB seeding script.

Idempotent: re-running on a fully-seeded file is a no-op (matches by id).

Responsibilities:
1. Reclassify two pre-existing entries that the v1→v2 migration carried over
   imperfectly:
     - `mental_health_post_disaster_1`: was `disaster_type=general,
       topic=first_aid`. Now `disaster_type=mental_health`, no topic. (O2.)
     - `cyclone_1`: was `phase=general`. The content describes the during-
       cyclone protocol; reclassify `phase=during`.

2. Append the new authored entries that bring the corpus to ~60 with
   per-bucket coverage per the locked Phase 2 decision (O1).

Sources:
- NDMA Pakistan (ndma.gov.pk)
- PMD (pmd.gov.pk)
- Pakistan Red Crescent (prcs.org.pk)
- AHA (heart.org)
- WHO (who.int)
- Geological Survey of Pakistan / USGS for earthquake science
- SSGC / SNGPL public safety advisories for gas-leak guidance

Run:
    python scripts/seed_kb_v2_phase2.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

TODAY = date.today().isoformat()


def _entry(
    *,
    id: str,
    disaster_type: str,
    phase: str,
    title: str,
    content: str,
    searchable_text: str,
    sources: list[dict],
    topic: str | None = None,
    disclaimer: bool = False,
) -> dict:
    out = {
        "id": id,
        "disaster_type": disaster_type,
        "phase": phase,
        "title": title,
        "content": content.strip(),
        "searchable_text": searchable_text,
        "sources": sources,
        "last_verified": TODAY,
        "disclaimer": disclaimer,
    }
    if topic:
        out["topic"] = topic
    return out


# ─── Source shorthand ─────────────────────────────────────────────────────────
NDMA = {"name": "NDMA Pakistan", "url": "https://ndma.gov.pk"}
PMD = {"name": "Pakistan Meteorological Department", "url": "https://www.pmd.gov.pk"}
PRCS = {"name": "Pakistan Red Crescent", "url": "https://prcs.org.pk"}
AHA = {"name": "American Heart Association", "url": "https://www.heart.org"}
WHO = {"name": "World Health Organization", "url": "https://www.who.int"}
USGS = {"name": "USGS Earthquake Hazards", "url": "https://www.usgs.gov/programs/earthquake-hazards"}
GSP = {"name": "Geological Survey of Pakistan", "url": "https://www.gsp.gov.pk"}
SSGC = {"name": "SSGC public safety advisories", "url": "https://www.ssgc.com.pk"}
SNGPL = {"name": "SNGPL public safety advisories", "url": "https://www.sngpl.com.pk"}
ROZAN = {"name": "Rozan Counseling Helpline", "url": "https://rozan.org"}
UMANG = {"name": "Umang Pakistan", "url": "https://umang.com.pk"}
RED_CROSS_FA = {"name": "Red Cross First Aid", "url": "https://www.redcross.org/take-a-class/first-aid"}


# ─── New entries ──────────────────────────────────────────────────────────────
NEW_ENTRIES: list[dict] = [
    # ── Earthquake (+4: prevention, recovery, school drills, vulnerable groups) ──
    _entry(
        id="earthquake.prevention.001",
        disaster_type="earthquake",
        phase="prevention",
        title="Earthquake risk reduction at home",
        content="""
**Earthquake risk reduction — long-horizon steps before any shaking starts.**

**1. Know your zone.** Northern Pakistan (GB, AJK, KPK Hazara, northern Punjab) is on the Hindukush-Himalayan thrust; Quetta-Chaman-Loralai is on the Chaman fault; Karachi/Gwadar coast lies near the Makran subduction. The 2005 Kashmir quake (M7.6) and 1935 Quetta quake (M7.7) are within living memory.

**2. Inspect your building.** Have unreinforced masonry (kacha, old RCC frames, hollow-block) checked by a structural engineer. Retrofit options: wall ties, base bolting, perimeter beam strengthening. Building Code of Pakistan (BCP-2021) is the legal floor for new construction.

**3. Anchor furniture.** Almirahs, water tanks, geysers, TVs, and kitchen shelves are the largest in-house injury cause. Use brackets to wall studs, not just plaster.

**4. Map your hazards.** Identify safe spots in each room (under sturdy desk, against an internal load-bearing wall — not a doorway). Mark gas main valve, electrical breaker, water shut-off. Photograph the layout.

**5. Plan the kit.** A minimum 3-day grab bag (see emergency kit guide), kept by the front door, refreshed every six months.

**6. Teach the household.** Children, elderly relatives, and domestic staff all need to know DROP-COVER-HOLD-ON before they need it.
""",
        searchable_text="earthquake prevention risk reduction retrofit anchor furniture pakistan building code bcp hindukush chaman makran",
        sources=[NDMA, GSP, USGS],
    ),
    _entry(
        id="earthquake.recovery.001",
        disaster_type="earthquake",
        phase="recovery",
        title="Recovery in the weeks after an earthquake",
        content="""
**Earthquake recovery — the first weeks after the immediate emergency.**

**1. Don't move back into a damaged structure.** Even if it looks intact, post-quake structural failure is a leading cause of secondary deaths (notably 2005 Kashmir aftershock collapses). Wait for an engineering assessment. PDMA and district administration coordinate inspection rounds.

**2. Document damage thoroughly.** Photographs of cracks, displacement, water/gas/electrical damage support BISP / Ehsaas relief and any insurance claim.

**3. Watch for delayed health issues.** Concrete dust exposure — chronic cough, irritated airways. Contaminated water — diarrhoea, cholera, hepatitis A/E. Mosquito-borne disease in standing water — dengue, malaria. Get medical attention early; children dehydrate fastest.

**4. Mental health is part of recovery.** Sleep disruption, hypervigilance, intrusive memories are normal in the first few weeks. If symptoms persist beyond a month or worsen — especially in children or those with prior trauma — call Rozan (0304-111-1741) or Umang (0311-7786264). Suicidal thoughts → call 115.

**5. Rebuild safer.** New construction must meet BCP-2021. Insist on a registered structural engineer signing off on any major repair.

**6. Stay alert for aftershocks for weeks.** Northern Pakistan saw M6+ aftershocks days and weeks after the 2005 mainshock. Keep your kit accessible.
""",
        searchable_text="earthquake recovery aftershock damage assessment structural inspection mental health rebuild bcp pdma bisp",
        sources=[NDMA, PRCS, WHO],
    ),
    _entry(
        id="earthquake.before.001",
        disaster_type="earthquake",
        phase="before",
        title="Earthquake preparedness for schools and households with children",
        content="""
**Drill before the disaster — protocols for households with children, elderly, and disabled members.**

**For children:**
- Teach DROP-COVER-HOLD-ON as a game. Repetition matters more than a single talk.
- Memorise one out-of-area relative's phone number. Stick it on the school bag.
- Identify the family meeting point outside the home and a backup if the first is blocked.
- Don't rely on phone reception — networks fail in the first hour after a major quake.

**For elderly relatives:**
- Pre-position the cane/walker next to where they sleep.
- Keep a 7-day medication supply in the grab bag.
- Pre-arrange a strong neighbour or relative who is responsible for them post-quake.
- Sleep on a lower floor where possible; avoid heavy headboards.

**For disabled household members:**
- Keep mobility aids, hearing aids, and spare batteries with the grab bag.
- Bracelet or laminated card with medical conditions, allergies, and emergency contact.
- If wheelchair-bound, identify the safest interior wall corner with no overhead hazards.
- Discuss the evacuation plan with anyone who would help.

**For schools:**
- Ministry of Federal Education / NDMA-endorsed quarterly drills.
- Ensure heavy classroom items (almirahs, projectors, science lab shelves) are anchored.
- Teachers know how to triage minor vs serious injuries until Rescue 1122 arrives.
""",
        searchable_text="earthquake before preparedness school drill children elderly disabled family plan vulnerable groups pakistan",
        sources=[NDMA, PRCS],
    ),
    _entry(
        id="earthquake.during.outdoors.001",
        disaster_type="earthquake",
        phase="during",
        title="Earthquake — outdoor and vehicle response",
        content="""
**If you are outdoors when the shaking starts:**

1. Move to a clear open area away from buildings, electricity poles, billboards, trees, and overhead signs. Falling masonry from cornices and parapets is the leading outdoor injury source in Pakistani urban centres.
2. Drop to the ground and protect your head and neck with your arms.
3. Stay away from unreinforced boundary walls — they tend to topple in M5+ shaking.
4. Wait until shaking stops AND debris settles before moving.

**If you are in a vehicle:**

1. Pull over in a safe spot — away from buildings, overpasses, flyovers, and power lines. Stay out of underpasses (Karachi, Lahore have several with structural concerns).
2. Stop, set the parking brake, stay inside with your seatbelt fastened.
3. Do not park under cantilever billboards or palm trees.
4. After shaking stops, watch for road damage — buckled asphalt, fallen wires, sinkholes.
5. Listen to FM 101 / PTV for road advisories before driving on.

**On a bridge or in a tunnel:**

- Bridge: keep moving forward off the bridge if you can do so safely.
- Tunnel: stop, stay in the vehicle, brace.

**On the coast (Karachi, Gwadar, Pasni, Jiwani):** Strong shaking near the Makran zone could be a tsunami precursor. Move inland to higher ground without waiting for an official warning. The 1945 Makran tsunami struck within minutes of the quake.

**Emergency numbers:** Rescue 1122 — Edhi 115 — NDMA 051-9205037.
""",
        searchable_text="earthquake during outdoor vehicle car bridge tunnel pakistan makran tsunami coast karachi gwadar",
        sources=[NDMA, USGS],
    ),

    # ── Flood (+3: prevention, recovery, vehicle-trapped) ──
    _entry(
        id="flood.prevention.001",
        disaster_type="flood",
        phase="prevention",
        title="Flood risk reduction — household and community level",
        content="""
**Flood risk reduction — what to do well before monsoon.**

**Household:**
- Raise electrical sockets, distribution boards, and the gas meter above past flood levels where you can.
- Install one-way valves on sewer lines if you live in low-lying urban areas (DHA Karachi, parts of Lahore Cantt, sections of Rawalpindi).
- Move boilers, geysers, and main breaker boxes to upper floors when feasible.
- Store property documents, CNICs, photos, and one week of medication in a waterproof zip bag, accessible at short notice.
- Build a small ramp / sandbag stash if you are in a known-flood area; canvas sandbags and sand are stocked at most district administration offices ahead of monsoon.

**Building:**
- Clear roof drains, gutters, and street-side nullahs before July. Encroachment on stormwater nullahs (Karachi, Lahore, Rawalpindi) is the single biggest urban flood multiplier.
- Roof waterproofing inspection annually — leaks turn into structural damage during sustained rain.

**Community:**
- Know your nearest pucca multi-storey building you can shelter in if water rises.
- Subscribe to PMD (pmd.gov.pk) and your provincial PDMA's Twitter / Facebook for early warnings. NDMA SMS alerts are activated for major events.
- Keep livestock tethering points identified on higher ground if you are in a riverine area (Indus, Chenab, Jhelum, Ravi, Sutlej, Kabul belts).

**Insurance / financial:**
- BISP / Ehsaas typically opens a flood relief window for affected districts. Keep your registration current.
""",
        searchable_text="flood prevention monsoon household nullah indus chenab jhelum drainage waterproof bisp pmd ndma pdma",
        sources=[NDMA, PMD, PRCS],
    ),
    _entry(
        id="flood.recovery.001",
        disaster_type="flood",
        phase="recovery",
        title="Flood recovery — weeks to months after the water recedes",
        content="""
**Flood recovery is a long phase. The displacement-and-disease tail is what kills most Pakistanis after a major flood (2010 and 2022 in particular).**

**1. Wait for an official all-clear before returning home.** District administration / PDMA announce when an area is safe.

**2. Before re-entering:**
- Mud-brick (kacha) walls collapse silently after prolonged saturation. Don't lean on them or put weight on roofs.
- Snakes, scorpions, and stray dogs displaced from fields take shelter in dry indoor spaces.
- Smell test for gas; if any suspicion, leave immediately and call 1199.
- Inspect electrical wiring before turning the breaker back on. Hire an electrician if standing water touched any junction.

**3. Health surveillance for 4–6 weeks:**
- Cholera, typhoid, hepatitis A/E from contaminated water. Boil drinking water 5+ minutes or use chlorine tablets until tap water is officially safe.
- Dengue, malaria post-flood mosquito boom — drain standing water in the house weekly, sleep under nets.
- Skin and eye infections from mud and contaminated water — early treatment matters.
- Children dehydrate within hours of diarrhoea. Get medical attention at the first sign of fever, vomiting, or watery stool.

**4. Documentation and relief:**
- Photograph all damage before cleaning.
- Register with the district BISP / Ehsaas relief window.
- Pakistan Red Crescent and Edhi run medical camps for weeks in affected districts.

**5. Rebuilding:**
- Reinforce masonry where possible. NDMA's Build Back Better guidelines target flood-resilient designs.
- Drain catchments around the home so the next monsoon doesn't re-flood the same low spot.

**6. Mental health.** Loss of home, livelihood, and community has a long psychological tail. See the mental health section. Rozan 0304-111-1741, Umang 0311-7786264.
""",
        searchable_text="flood recovery cleanup health cholera dengue rebuild bisp pakistan red crescent mud brick electrical mental health",
        sources=[NDMA, WHO, PRCS],
    ),
    _entry(
        id="flood.during.vehicle.001",
        disaster_type="flood",
        phase="during",
        title="Flood — what to do when your vehicle is in rising water",
        content="""
**A vehicle in rising flood water is one of the most dangerous places to be. 60 cm of moving water can sweep an SUV.**

**If water is rising and you are still moving:**
1. **Turn around. Do not cross.** "Turn around, don't drown" is not a slogan — it is a survival rule. Most flood vehicle deaths happen on familiar routes drivers thought they could read.
2. Avoid underpasses (Karachi's Liaquatabad, Mall Road Lahore, several Pindi underpasses fill within minutes during heavy rain).
3. Avoid bridges over fast-rising rivers.

**If water has reached your wheels but you are stopped:**
1. Restart the engine only if the air intake is well above water. Hydrolock is permanent damage.
2. Slowly reverse onto higher ground if the road behind is clear.
3. If the engine is dead, do not crank repeatedly — flooded cylinders bend rods.

**If water is up to the doors and rising:**
1. **Get out. Now.** Do not wait for the water to "go down a bit."
2. Open the door before water reaches the window. Once it does, door pressure makes opening near-impossible.
3. If a door won't open: lower an electric window if the system still works, or break the side window with a centre-punch / glass-breaker. Side and rear windows are tempered and shatter; the windshield is laminated and will not.
4. Climb onto the roof if the surrounding water is deeper than knee-high. Wait for rescue.
5. If you must wade, use a stick to probe ahead — open manholes are the hidden killer in urban floods.

**Call:** Rescue 1122. Give the road, nearest landmark, and direction of travel. Stay on the line.
""",
        searchable_text="flood vehicle car trapped rising water hydrolock window break karachi underpass urban flood",
        sources=[NDMA, PRCS],
    ),

    # ── Heatwave (+3: prevention, before, recovery) ──
    _entry(
        id="heatwave.prevention.001",
        disaster_type="heatwave",
        phase="prevention",
        title="Heatwave prevention — building hydration and cooling habits before peak summer",
        content="""
**Heatwaves now arrive earlier and harder in Sindh and southern Punjab. Karachi 2015 (>1,200 deaths) is the modern reference point.**

**Build the hydration habit in March-April:**
- Adults: 2.5–3 L water per day baseline. Add 1 L per hour of outdoor work.
- Outdoor workers (mazdoors, riders, traffic police, construction): set hourly drink reminders.
- Keep a water bottle within arm's reach during the day.
- ORS sachets at home and in the car. One sachet in 1 L water.
- Avoid alcohol, excessive paan/gutka, and high-caffeine drinks — they dehydrate.

**Make the home heat-tolerant:**
- Light-coloured roof paint or chuna lowers indoor temperature by several degrees.
- Heavy curtains on west-facing windows.
- Cross-ventilation: identify which windows to open at night.
- Keep one room as the "cool zone" — windowless or with the strongest fan/AC. Fall back to it during peak heat.
- Stock a basic cooling kit: fan, wet towels, ice, ORS.

**Vehicle:**
- Never leave children, elderly, or pets in a parked vehicle even briefly. Interior temperatures pass 50°C in minutes in May–June.
- Sunshade for the windshield. Keep one extra litre of water in the boot during summer.

**Plan for power cuts:**
- Load shedding peaks during heatwaves. UPS, battery fans, power banks.
- Check on neighbours who don't have backup, especially elderly living alone.
""",
        searchable_text="heatwave prevention hydration ors karachi sindh punjab cooling home power outage habits summer",
        sources=[NDMA, PMD, WHO],
    ),
    _entry(
        id="heatwave.before.001",
        disaster_type="heatwave",
        phase="before",
        title="Heatwave — what to do when PMD issues an alert",
        content="""
**PMD heatwave alerts typically run 24–72 hours ahead. Use the lead time.**

**Watch and stock:**
- Confirm the alert via PMD (pmd.gov.pk) or NDMA. WhatsApp forwards are not authoritative.
- Stock 3+ days of water (4 L per person per day minimum). Tap supply often fails during peak heat.
- Stock ORS (4–6 sachets per household), light food, fruit (watermelon, cucumber, citrus).
- Charge phones, power banks, battery fans. Test the UPS.

**Reschedule:**
- Move outdoor work, errands, sports to before 11 AM or after 5 PM.
- Reschedule elderly relatives' clinic visits if possible.
- Check on neighbours and domestic staff who work outdoors.

**Vulnerable groups need a check-in plan:**
- Elderly living alone — phone or visit twice a day during the alert.
- Pregnant women, infants — keep cool, drink frequently, watch for distress.
- People with heart, kidney, or diabetic conditions — stay indoors during peak.
- Outdoor workers — hourly water + shade breaks; OSH-Pakistan circulars apply.

**Recognise heat stroke early (call 115 / 1122):**
- Body temperature 40°C+, hot dry skin (no sweating)
- Confusion, slurred speech, severe headache
- Rapid pulse, loss of consciousness

**First-aid stop-gap while waiting for ambulance:**
- Move to coolest space. Remove excess clothing.
- Wet cloths to neck, armpits, groin (major arteries cool fastest).
- Fan vigorously. If conscious, sip cool water or ORS.
- Do NOT give fluids if unconscious — choking risk.
""",
        searchable_text="heatwave before alert pmd ndma stock ors elderly outdoor workers heat stroke karachi sindh punjab",
        sources=[NDMA, PMD, WHO],
        disclaimer=True,
    ),
    _entry(
        id="heatwave.recovery.001",
        disaster_type="heatwave",
        phase="recovery",
        title="Heatwave recovery — watching for cumulative damage after the heat breaks",
        content="""
**Even after the heatwave passes, several conditions show up over the following days.**

**Watch in the 7–10 days after:**
- Persistent fatigue, headaches, dizziness — possible delayed dehydration.
- Dark urine, low urine output — kidney stress. Push fluids; if no improvement in 24 hours, see a doctor.
- New muscle cramps, especially at night — electrolyte depletion. ORS, banana, dates.
- Heart palpitations, chest discomfort in elderly or cardiac patients — same-day medical review.
- Mood changes, low mood, sleep disruption — heat fatigue is real and recovery takes a week or more.

**For someone who survived a heat-stroke episode:**
- Follow the discharging hospital's protocol: rest, hydration, no outdoor exertion for at least a week.
- Monitor for kidney function, neurological symptoms — ER follow-up if anything seems off.
- Avoid further heat exposure for at least 2 weeks; the body's heat regulation is impaired post-stroke.

**Resupply:**
- ORS, water bottles, fan batteries — prepare for the next alert. Pakistan's heatwave season runs May–early July and increasingly into October in the coastal belt.

**Community:**
- Check on elderly neighbours. Heat-related deaths often come to light days after the worst day, when someone notices the absence.

**Helplines:** 115 (Edhi ambulance), 1122 (Rescue), nearest DHQ hospital.
""",
        searchable_text="heatwave recovery aftermath dehydration kidney elderly heat stroke followup pakistan",
        sources=[NDMA, WHO],
    ),

    # ── Cyclone (+3: prevention, before, after — existing cyclone_1 reclassified to during) ──
    _entry(
        id="cyclone.prevention.001",
        disaster_type="cyclone",
        phase="prevention",
        title="Cyclone risk reduction — coastal Sindh and Balochistan",
        content="""
**The Arabian Sea is producing more named cyclones in the coastal belt: Yemyin (2007), Phet (2010), Biparjoy (2023), Asna (2024). Cyclone seasons: May–June and October–November.**

**Where you live and build matters most:**
- Setbacks from the high-tide line are non-negotiable in Gwadar, Pasni, Jiwani, Ormara, Karachi DHA Phase 8, Ibrahim Hyderi.
- Single-storey concrete with a flat roof and shutters resists wind better than tin or thatch.
- Window shutters / steel mesh save lives. Most cyclone injuries are from broken window glass.
- For new builds: PDMA Sindh and PDMA Balochistan publish wind-load standards.

**Boats and livelihoods:**
- Identify a high-ground tethering point inland for fishing boats during the May–June and Oct–Nov windows.
- Insure where you can. Sindh / Balochistan livelihoods schemes activate during cyclone declarations.

**Documents and supplies:**
- Waterproof zip bag with CNICs, property papers, photos.
- 5+ days of food, water, batteries, ORS, basic medication. Coastal supply chains break for a week minimum.
- Battery radio or hand-crank radio. Mobile networks fail.

**Community plans:**
- Know the nearest cyclone shelter (PDMA designates schools and government buildings as shelters during emergencies).
- A pre-arranged inland relative or friend you can stay with for several days.
- Phone tree: who calls whom when an alert is issued.

**Subscribe to alerts:** PMD (pmd.gov.pk), PDMA Sindh, PDMA Balochistan, NDMA — all post real-time during a watch.
""",
        searchable_text="cyclone prevention coastal sindh balochistan gwadar karachi pasni jiwani biparjoy boats setback wind shutters pdma",
        sources=[NDMA, PMD],
    ),
    _entry(
        id="cyclone.before.001",
        disaster_type="cyclone",
        phase="before",
        title="Cyclone preparedness — the 48 hours after a watch is issued",
        content="""
**Cyclone watches are issued 48–72 hours out. Use that window.**

**24–48 hours out:**
- Confirm the alert with PMD (pmd.gov.pk). Note the projected landfall window and category.
- Track via radio (FM 101, BBC Urdu, local stations) and PDMA Sindh / Balochistan social media.
- Top up fuel for vehicles. Pumps run dry in the last 12 hours before landfall.
- Withdraw cash. ATMs fail in coastal areas during outages.
- Charge every phone, power bank, and battery-operated lamp.

**12–24 hours out:**
- Move boats inland. Tie them above the projected high-water mark.
- Bring outdoor furniture, plant pots, corrugated sheets indoors. Anything light becomes a missile.
- Tape windows in an X pattern (reduces glass spray) or fit shutters / plywood.
- Move valuables and electronics to the highest interior floor.
- Top up water containers — 5+ litres per person per day for 5 days.
- Test the battery radio.

**6–12 hours out:**
- Eat a full meal — cooking later may not be possible.
- Move livestock to higher ground if you can do so safely.
- Go to the cyclone shelter if you live in a low-lying coastal area or in non-pucca housing.
- Take essentials only: CNIC, cash, medications, phones, chargers, water, light food.

**If officials order evacuation:** go. The single most fatal decision in past Pakistan cyclones was to ignore the order in the last 6 hours.

**Helplines:** 1122, 115, PDMA Sindh 021-99211530, PDMA Balochistan 081-9202186.
""",
        searchable_text="cyclone before preparedness watch alert evacuation shelter coastal sindh balochistan boats supplies pmd pdma",
        sources=[NDMA, PMD],
    ),
    _entry(
        id="cyclone.after.001",
        disaster_type="cyclone",
        phase="after",
        title="Cyclone aftermath — what to do once the eye has passed",
        content="""
**Most cyclone deaths happen AFTER landfall, not during.** Storm surge, downed power lines, contaminated water.

**Do not go outside until the official all-clear.** The eye of the storm is a temporary calm that will be followed by winds from the opposite direction, often more violent.

**Once authorities declare safe:**

**1. Hazards to expect:**
- Downed power lines. Treat every wire as live. Stay 10 m away. Call WAPDA 118.
- Storm surge can persist for hours after landfall. Coastal areas may still be flooding.
- Broken glass, twisted metal sheets, fallen trees.
- Snakes and stray animals displaced inland.

**2. Check on others:**
- Elderly neighbours, anyone with mobility issues.
- Children — separated children should be brought to the nearest police post or PDMA shelter.

**3. Health:**
- Open wounds need cleaning + tetanus consideration. DHQ hospitals run free emergency care.
- Drinking water is contaminated — boil 5+ minutes or use chlorine tablets until officials confirm tap supply is safe.
- Watch for cholera, typhoid, hepatitis in the days following. Diarrhoea + fever in a child needs same-day medical attention.

**4. Document and report:**
- Photograph damage before cleaning.
- Register with PDMA / district administration for relief.
- BISP / Ehsaas opens a relief window for declared cyclone districts.

**5. Don't return to a damaged structure** until a structural engineer or PDMA team clears it. Roofs and walls often fail days after the wind has stopped.

**Helplines:** 1122, 115, NDMA 051-9205037, WAPDA 118.
""",
        searchable_text="cyclone after aftermath storm surge downed lines health cholera shelter pdma bisp coastal pakistan",
        sources=[NDMA, WHO, PRCS],
    ),

    # ── Fire (+3: prevention, multistorey, after) ──
    _entry(
        id="fire.prevention.001",
        disaster_type="fire",
        phase="prevention",
        title="Fire prevention — household checklist",
        content="""
**Most home fires in Pakistan start from cooking, electrical faults, or LPG cylinders.**

**Smoke detectors (the highest-impact intervention):**
- Battery-powered smoke alarms are inexpensive and lifesaving. One per bedroom and one near the kitchen entry.
- Test monthly, replace batteries yearly, replace the unit every 10 years.

**Kitchen:**
- Never leave cooking oil unattended.
- Keep a fire blanket or large lid within arm's reach of the stove.
- Don't store flammable items (cooking oil, paper, plastic containers) close to the burner.
- LPG cylinders: ISO/PSQCA-marked only, kept upright, away from heat, with a pressure regulator in good condition.
- Replace rubber gas hoses annually — cracked rubber is the #1 cylinder fire cause.

**Electrical:**
- Don't overload power strips. Multiple high-load appliances (geyser, AC, microwave) on one strip is a fire risk.
- Replace frayed wires immediately. Don't bypass tripping breakers.
- Avoid kacha extensions (twisted wires without proper sleeves) in plug points.
- Have your earthing checked.

**Heaters and geysers:**
- Gas heaters should not be left running overnight or in sealed rooms — CO poisoning kills more Pakistanis in winter than people realise.
- Geyser placement: well-ventilated, never inside a small bathroom.

**Escape plan:**
- Two ways out of every room.
- Family meeting point outside the home.
- Practice the escape with kids twice a year.

**What to keep ready:**
- Fire extinguisher (CO2 or dry chemical) in the kitchen and near the main panel.
- A working flashlight by the bed.
- Phone numbers for 16 (Fire) and 1122 (Rescue) saved.
""",
        searchable_text="fire prevention home kitchen electrical lpg cylinder smoke detector escape plan pakistan ssgc sngpl",
        sources=[NDMA, SSGC, SNGPL],
    ),
    _entry(
        id="fire.during.multistorey.001",
        disaster_type="fire",
        phase="during",
        title="Fire in a multi-storey building",
        content="""
**Fires in older Pakistani multi-storey buildings (Saddar Karachi, Old Lahore, Rawalpindi commercial areas) are deadlier because of single staircases, poor ventilation, and combustible interior finishes.**

**If the alarm sounds or you see smoke / smell burning:**

**1. Use stairs. Never the elevator.** Lifts go to the fire floor. They can also lose power and trap occupants.

**2. Test every door before opening.**
- Touch with the back of your hand. If it's hot, do not open.
- Use another route.

**3. Crawl below the smoke.** Cleaner air is closer to the floor. Keep one hand on a wall to navigate.

**4. Close doors behind you.** Each closed door buys you 10–20 minutes. This is what fire-resistance ratings are for.

**5. If the corridor is impassable:**
- Return to a room with a closeable door.
- Seal the door bottom with wet towels / clothing.
- Open a window — but do not break it unless the room is filling with smoke.
- Wave a bright cloth from the window. Call 1122 and 16 from inside; tell them your exact floor and side of the building.

**6. If clothing catches fire:** Stop, drop, roll. Running fans the flames.

**7. After you exit:**
- Stay out. Do NOT go back for belongings, pets, or other people unless trained.
- Move at least 100 m from the building. Walls and glass continue to fail for hours.
- Account for everyone at the family meeting point.

**Multi-tenancy issues common in Pakistan:**
- Many older commercial buildings have only one staircase. Know yours BEFORE there's a fire.
- Locked roof access cuts off the secondary escape route. Petition building management.
- Combustible cladding / decorations in shopping plazas — be aware on busy weekends.

**Helplines:** 16 (Fire), 1122 (Rescue), 115 (Edhi).
""",
        searchable_text="fire multistorey high rise building escape stairs elevator smoke karachi lahore commercial saddar",
        sources=[NDMA, PRCS],
    ),
    _entry(
        id="fire.after.001",
        disaster_type="fire",
        phase="after",
        title="After a fire — re-entry, health, and rebuilding",
        content="""
**Once Rescue 1122 / fire brigade declares the scene safe.**

**1. Do not enter without authorisation.** Walls may collapse hours after the flames are out. Roofs warp under heat and fail later. The fire department's all-clear is the gate.

**2. Health first:**
- Smoke inhalation symptoms can show up hours later — persistent cough, hoarse voice, shortness of breath, headache, nausea. Get evaluated. AKUH, JPMC, Mayo, PIMS run 24/7 emergency.
- Carbon monoxide is invisible and odourless. Anyone who was in heavy smoke needs an ER review.
- Burn wounds: cover with clean dry cloth, see a hospital — even small burns can become serious infections without proper care.

**3. Document:**
- Photograph everything before cleaning.
- Save receipts for any temporary lodging, repairs, replacement essentials.
- Get a fire department incident report — required for most insurance claims and government relief.

**4. Utilities:**
- Do NOT switch on power until the wiring has been inspected by an electrician.
- Do NOT use the gas line until SSGC / SNGPL has inspected (1199).
- Boil any water from a fire-affected supply for 5+ minutes until the utility confirms it is safe.

**5. Salvage:**
- Sort items into clean / smoke-damaged / destroyed.
- Smoke odour penetrates fabric, paper, and porous surfaces. Professional cleaning may be required.
- Dispose of any food that was in a fire-affected room — heat damages packaging seals.

**6. Mental health:**
- Anxiety, sleep disruption, hypervigilance to smoke smells are common. Most ease in 2–4 weeks.
- If symptoms persist or worsen, especially in children, call Rozan 0304-111-1741 or Umang 0311-7786264.

**Helplines:** 16, 1122, 115, 1199 (gas), 118 (WAPDA).
""",
        searchable_text="fire after aftermath smoke inhalation carbon monoxide rebuild insurance ssgc sngpl wapda mental health",
        sources=[NDMA, WHO, PRCS],
    ),

    # ── Gas leak (+3: prevention, cylinder, after) ──
    _entry(
        id="gas_leak.prevention.001",
        disaster_type="gas_leak",
        phase="prevention",
        title="Gas leak prevention — pipes, cylinders, and geysers",
        content="""
**Gas-related deaths in Pakistan span three distinct sources: cylinder leaks, SNGPL/SSGC piped-gas leaks, and CO poisoning from geysers and gas heaters in winter.**

**Piped gas (SNGPL Punjab/KPK, SSGC Sindh/Balochistan):**
- Annual safety inspection. Both utilities offer free leak checks on request.
- Inspect rubber hoses where they meet the regulator and the appliance — replace if cracked, hardened, or older than 1 year.
- The gas main valve location must be known to every adult in the home.
- Don't seal kitchen ventilation. Gas accumulating in a sealed space is what causes the worst incidents.

**LPG cylinders:**
- Use only ISO / PSQCA-marked cylinders from registered dealers.
- Keep cylinders upright, in a well-ventilated space, away from any heat source.
- Test the connection with soapy water — bubbles indicate a leak.
- Don't store cylinders in the kitchen if possible; a separate ventilated cubicle is safer.
- Replace the regulator every 5 years. Cheap regulators leak.

**Geysers (winter season):**
- Place in a well-ventilated area. NEVER inside a small bathroom — CO buildup can kill within minutes.
- Annual servicing of the burner, flue, and rubber seals.
- Symptoms of CO poisoning: headache, dizziness, nausea, drowsiness, confusion. Get fresh air and call 115.
- Battery-powered CO alarms are inexpensive — install one near every gas appliance.

**Heaters:**
- Gas heaters need ventilation. A cracked window is enough.
- Turn off when leaving the room or sleeping.

**What to do at the first whiff of gas:** see the during-leak entry.

**Helplines:** SSGC/SNGPL 1199, Rescue 1122, Fire 16.
""",
        searchable_text="gas leak prevention sngpl ssgc cylinder geyser carbon monoxide winter pakistan safety check ventilation",
        sources=[SSGC, SNGPL, NDMA],
    ),
    _entry(
        id="gas_leak.during.cylinder.001",
        disaster_type="gas_leak",
        phase="during",
        title="LPG cylinder leak — immediate response",
        content="""
**A leaking cylinder is more dangerous than a leaking pipe — there is more gas under more pressure, and a BLEVE (boiling-liquid expanding vapour explosion) is a catastrophic failure mode.**

**The instant you suspect a cylinder leak (smell of mercaptan / "rotten egg", hissing, frost on the valve):**

**1. DO NOT:**
- Switch any electrical on or off. The spark from a switch is enough to ignite gas.
- Use mobile phones inside the building.
- Light matches, lighters, candles.
- Ring doorbells, intercoms, fans, ACs.

**2. DO:**
- Open every window and door immediately. Cross-ventilation pushes gas out.
- Turn off the cylinder valve (clockwise) at the top of the cylinder.
- Get everyone out of the building.
- Carry the cylinder outdoors to an open area — but ONLY if you can do so safely. Keep it upright. If the leak is severe (loud hissing, frost, fire near the valve) — leave it and evacuate.
- From outside, at a safe distance (at least 50 m), call 1199 and 16.
- Warn neighbours.

**3. If the cylinder is on fire:**
- Do NOT try to extinguish the flame. A burning leak is safer than an unburnt one because the gas is being consumed as it escapes.
- Evacuate to 100+ m. Keep everyone behind concrete or earth cover if possible.
- Call 16 and 1122 immediately.
- Wait for the fire brigade. They will cool the cylinder and let the fire burn out.

**4. After the leak is contained:**
- Do not return until the gas company / fire department has cleared the building.
- Have your gas connections, cylinder valve, regulator, and rubber hose all replaced or inspected.
- Ventilate the building thoroughly before any electrical use.

**Helplines:** 1199 (SSGC/SNGPL), 16 (Fire), 1122, 115.
""",
        searchable_text="gas leak cylinder lpg bleve fire emergency ventilation valve sngpl ssgc pakistan",
        sources=[SSGC, SNGPL, NDMA],
    ),
    _entry(
        id="gas_leak.after.001",
        disaster_type="gas_leak",
        phase="after",
        title="After a gas leak — re-entry and inspection",
        content="""
**The aftermath of a gas leak is its own risk window. Residual gas, weakened seals, and CO exposure can all cause harm after the immediate scare is over.**

**Do not re-enter the building** until SSGC/SNGPL or the fire department clears it. They will use a gas detector that is far more sensitive than human smell.

**Once cleared:**

**1. Inspection (have an authorised technician, not a casual plumber):**
- Replace the leaking component plus any adjacent hose/regulator/valve.
- Pressure-test the line from the meter to each appliance.
- Check appliance burners — yellow flame indicates incomplete combustion (CO risk); the flame should be blue.

**2. Ventilation:**
- Keep windows open for several hours after re-entry, even if you can no longer smell gas.
- Run kitchen exhausts. Don't seal vents back up immediately.

**3. Health follow-up — within 24–48 hours:**
- If anyone was in the gassy space, watch for delayed CO symptoms: persistent headache, dizziness, fatigue, nausea, confusion, chest pain.
- Pregnant women, infants, elderly, and anyone with cardiac conditions should be evaluated at a hospital even after a brief exposure.
- Get a baseline pulse oximetry reading; CO can drop oxygen delivery without lowering SpO2 (CO-Hgb mimics oxygen on most pulse oximeters), so trust symptoms over the number.

**4. Documentation:**
- Save the SSGC/SNGPL service report.
- Photographs of the leaking component and any damage.
- Insurance and tenancy disputes both rely on this paperwork.

**5. Prevention going forward:**
- See the gas-leak prevention entry.
- Annual safety inspection — both utilities offer free leak checks.
- Replace rubber hoses yearly; replace regulators every 5 years.

**Helplines:** SSGC/SNGPL 1199, Rescue 1122, Edhi 115.
""",
        searchable_text="gas leak after aftermath inspection sngpl ssgc carbon monoxide health cylinder pakistan ventilation",
        sources=[SSGC, SNGPL, WHO],
    ),

    # ── Building collapse (+3: before-retrofit, during-witness, after) ──
    _entry(
        id="building_collapse.before.001",
        disaster_type="building_collapse",
        phase="before",
        title="Building collapse prevention — retrofitting and recognising warning signs",
        content="""
**Pakistan has a long history of structural collapses outside of earthquakes: Margalla Towers (2005, foundation failure post-quake), Karachi residential blocks (recurring), Lahore factory collapses, illegal additions on older RCC frames.**

**Warning signs that a building is failing (call PDMA / Rescue 1122):**
- New diagonal cracks in load-bearing walls. Diagonal = shear failure.
- Cracks that appear or widen rapidly over days/weeks.
- Doors and windows that no longer close properly because frames have shifted.
- Sloping floors. Visibly tilted exterior walls.
- Concrete spalling — exterior concrete cracking off and exposing rebar. Especially after rain/monsoon.
- Sounds: groaning, creaking, popping when someone walks across a floor.
- Sagging beams or floors.

**Risk factors for an existing building:**
- Built before BCP-2007 enforcement (Building Code of Pakistan) — most older urban housing.
- Illegal additional floors. The original foundation was not designed for the added load.
- Sub-standard construction (wrong cement-to-sand ratio, undersize rebar, hollow blocks where solid was specified).
- Adjacent excavation / construction undermining the foundation.
- Recent flooding around the foundation.
- Earthquake history without a structural inspection afterwards.

**What to do:**
- Hire a registered structural engineer for a condition assessment. Several PEC-licensed firms offer one-day visual inspections.
- Request a PDMA / district administration vulnerability survey if you suspect the building is genuinely unsafe.
- Don't rely on a contractor's verbal "it's fine."
- Retrofit options vary by building type — wall ties, base bolting, jacketing of columns, additional moment frames. Costs scale with severity.

**If the engineer flags it as unsafe and you can't afford a retrofit:** evacuate, document, file with PDMA. Loss of housing is real but loss of life is permanent.

**Helplines:** PDMA Punjab 042-99205316, PDMA Sindh 021-99211530, PDMA KPK 091-9212689, NDMA 051-9205037.
""",
        searchable_text="building collapse before prevention retrofit warning signs cracks structural engineer pec bcp pakistan",
        sources=[NDMA, GSP],
    ),
    _entry(
        id="building_collapse.during.witness.001",
        disaster_type="building_collapse",
        phase="during",
        title="Witnessing a building collapse",
        content="""
**If you see a building collapse — or are nearby when one happens — your first job is to NOT become a second casualty.**

**1. Move to a safe distance.** At least 100 m, preferably with concrete cover between you and the building. Secondary collapses are common in the minutes and hours after the initial failure.

**2. Call Rescue 1122 immediately.** Provide:
- Exact street address + nearest landmark + district.
- Approximate number of people you think were inside.
- Any visible hazards: gas line ruptures, electrical sparks, fire, water main breaks.
- Whether you can see any survivors at the surface.

**3. Keep bystanders away.** Crowds at a collapse site:
- Get hurt by secondary collapses.
- Block ambulances and fire engines.
- Move debris in ways that crush or suffocate trapped survivors below.

**4. DO NOT dig** unless you are part of an organised SAR team. Untrained digging is the leading cause of preventable trapped-survivor deaths. You can:
- Cause secondary collapse.
- Cut survivors with displaced rebar / glass.
- Suffocate them by collapsing the small air pocket that's keeping them alive.

**5. What you CAN safely do:**
- Listen for tapping, voices. Note the location and tell first responders.
- Mark the perimeter so others stay back.
- Direct ambulance / fire to the entrance.
- Note the time of collapse — it matters for rescue planning.

**6. After Rescue 1122 takes charge:** follow their instructions. Pakistan Army Engineering Corps deploys for major incidents and they run the scene; civilian helpers are valuable when organised.

**Pakistan SAR resources:**
- Rescue 1122 has urban-SAR teams in major cities.
- Pakistan Army Engineering Corps for large incidents.
- Civil Defence assists with scene management.

**Helplines:** 1122, 115, 1199 (gas), 16 (fire).
""",
        searchable_text="building collapse witness rescue 1122 sar urban search rescue pakistan army secondary collapse",
        sources=[NDMA, PRCS],
    ),
    _entry(
        id="building_collapse.after.001",
        disaster_type="building_collapse",
        phase="after",
        title="After a building collapse — affected residents and neighbours",
        content="""
**For anyone displaced by a collapse, or living in an adjacent building.**

**1. Don't go back in.** Even if your unit looks fine, the structure may have lost integrity. Wait for a structural engineer's clearance.

**2. Adjacent buildings:**
- Have your building re-inspected. Foundation movement on one side often affects the next.
- Watch for new cracks over the following days.
- If your building shares a wall with the collapsed one, evacuate as a precaution and request a PDMA survey.

**3. For residents who survived being trapped:**
- ER evaluation is mandatory even if you walked out. Crush injuries, internal bleeding, rhabdomyolysis can show up hours later.
- Mental-health support: PTSD, sleep disruption, hypervigilance are normal after entrapment. Reach out — Rozan 0304-111-1741, Umang 0311-7786264.
- Compensation and rehousing: file with district administration and PDMA. NGO support (Edhi, Chhipa, Saylani) often runs in parallel.

**4. Documentation:**
- Photographs of the collapse and your unit before any clean-up.
- Lease, property documents, inventory of lost belongings (best you can recall).
- The fire / Rescue 1122 incident report.

**5. Investigation:**
- Major collapses are typically followed by NDMA / PDMA / district investigations. Cooperate fully.
- If the building's owner / contractor was cutting corners, the case may go to court. Documentation is your only leverage.

**6. Long term:**
- Don't rush to move into another older building without a structural assessment.
- Learn the warning signs (see the prevention entry) so you can move out of the next failing building before it fails.

**Helplines:** 1122, 115, NDMA 051-9205037, PDMA local.
""",
        searchable_text="building collapse after aftermath survivor neighbour displacement pdma structural inspection mental health pakistan",
        sources=[NDMA, PRCS, WHO],
    ),

    # ── Electric shock (4 entries) ──
    _entry(
        id="electric_shock.prevention.001",
        disaster_type="electric_shock",
        phase="prevention",
        title="Electric shock prevention — Pakistan-specific household risks",
        content="""
**Electric shock is one of the most common preventable injuries in Pakistan: kacha electrical extensions, water-logged streets in monsoon, illegal connections, faulty earthing.**

**Highest-impact household interventions:**

**1. Earthing.** Have a qualified electrician check the earthing resistance. Anything above ~5 ohms is bad. Earthing is what saves you when an appliance casing develops a fault.

**2. Residual current device (RCD / ELCB / GFCI).** A 30 mA RCD on the bathroom and outdoor circuits trips on body-leakage current and can save a life. Inexpensive; require an electrician for installation.

**3. Replace kacha extensions.** Twisted bare wires in plug points are electrical Russian roulette. Use moulded multi-plugs with built-in fuses.

**4. Don't overload.** Geyser + AC + microwave on one strip is a fire and shock risk. Distribute load across circuits.

**5. Bathroom safety.**
- No portable heaters or extension cords in the bathroom.
- Geyser switch outside the bathroom or with proper damp-rated enclosure.
- Don't touch any switch with wet hands.

**6. Outdoor and rooftop:**
- Don't fly kites near power lines (a recurring monsoon-season fatality).
- During load-shedding, never poke at a streetlight pole or transformer.
- Do not stand on a wet roof and touch any installed electrical fitting.

**7. Monsoon-specific:**
- Avoid puddles near transformers, electric poles, KE / LESCO junction boxes — flooded water around these is electrified.
- Switch off the main breaker BEFORE flood water enters the home.
- After flooding, do not re-energise until an electrician inspects.

**8. Children:**
- Plug-point safety covers.
- Keep extension cords coiled and out of reach.

**Symptoms warranting a 115/1122 call even after a "minor" shock:**
- Loss of consciousness, even briefly.
- Burns at entry/exit points.
- Chest pain, irregular heartbeat.
- Confusion.
- Any high-voltage exposure (lightning, transformer, overhead line).

**Helplines:** 115 (Edhi), 1122 (Rescue), 118 (WAPDA / power emergency), KE (Karachi) 118.
""",
        searchable_text="electric shock prevention household earthing rcd bathroom monsoon kacha extension wapda lesco ke pakistan",
        sources=[PRCS, NDMA],
    ),
    _entry(
        id="electric_shock.during.isolation.001",
        disaster_type="electric_shock",
        phase="during",
        title="Electric shock — isolating power and rescuing the victim",
        content="""
**The first rule of electric-shock rescue: do NOT touch a victim still in contact with live electricity. You will become the next casualty.**

**Step 1: Cut the power.**

- Find the main breaker / mains switch and turn it off.
- For a single appliance: unplug it at the wall (use a dry hand, dry footing).
- For a household / building: turn off the main MCB at the meter cabinet.

**If you cannot reach the breaker:**

- Use a **dry, non-conductive object** to push the source away from the victim.
  - Dry wooden stick, broom handle, plastic chair leg — these are insulators if dry.
  - Never use anything metal, never use anything wet.
- Stand on a dry surface — rubber mat, dry plastic, dry wooden plank.
- Push the source away from the victim, not the other way around.

**For high-voltage exposure (overhead lines, transformer, lightning strike):**

- Stay AT LEAST 10 m AWAY. High-voltage current can arc through the air to anyone within ~6 m.
- Do not approach. Do not let bystanders approach.
- Call WAPDA (118) and Rescue 1122 immediately.
- Wait for the line to be confirmed de-energised before any rescue attempt.
- "Step voltage" — voltage gradient in the ground around a downed line — can shock you through your feet. If you have to retreat from a downed line, hop with feet together or shuffle in tiny steps.

**Step 2: Once safe to touch.**

- Check responsiveness — tap shoulder firmly, shout.
- Check breathing. If absent or only gasping: start hands-only CPR (see CPR card).
- Call **115 / 1122** immediately. Stay on the line.

**Step 3: Even minor shocks need ER review.**

- Internal injuries (heart rhythm, kidney damage from rhabdomyolysis) are not visible.
- Brief loss of consciousness, however short → ER.
- Chest pain or irregular heartbeat → ER.
- Burns at entry/exit → ER.

**Step 4: Don't let the victim refuse the hospital.** Many electric-shock victims feel "fine" for the first hour and then have cardiac arrhythmias hours later.

**Helplines:** 115, 1122, 118 (WAPDA), KE 118.

⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For serious injuries or medical emergencies, call **115** or **1122** immediately. Do not attempt procedures beyond your training.
""",
        searchable_text="electric shock during isolation rescue power breaker overhead line wapda step voltage cpr pakistan",
        sources=[PRCS, RED_CROSS_FA],
        disclaimer=True,
    ),
    _entry(
        id="electric_shock.during.assessment.001",
        disaster_type="electric_shock",
        phase="during",
        title="Electric shock — assessing the victim once safe to touch",
        content="""
**Once the source is de-energised and the victim is safe to touch, the priority is assessing what you cannot see.**

**1. ABC: Airway, Breathing, Circulation.**
- Airway: tilt head, lift chin. Clear obstructions.
- Breathing: look, listen, feel for 5–10 seconds. Chest rise. Normal rhythm.
- Circulation: pulse at the carotid (neck) or radial (wrist).

**2. If not breathing or only gasping → CPR.**
- See the CPR first-aid card. Hands-only CPR for adults: centre of chest, hard and fast, 100–120 compressions per minute.
- Call 115 / 1122 immediately. Put the phone on speaker — operators guide you.

**3. If breathing but unconscious:**
- Place in the recovery position (on their side).
- Keep airway open.
- Don't move them if you suspect a fall or spine injury — stabilise the head between two firm objects (rolled towels) and wait for paramedics.

**4. If conscious and walking:**
- They still need ER review. Cardiac arrhythmias, internal burns, kidney injury can develop hours later.
- Don't let them refuse the hospital.

**5. Visible burns:**
- Cover with a clean dry cloth. Don't apply creams, butter, toothpaste, sui-gas paste, or anything else.
- Note the entry and exit points — this is what the ER team needs to know.

**6. Falls from height:**
- Many electric-shock injuries come with a secondary fall (off a ladder, off a roof). Treat as suspected spine injury until cleared.
- Do not let the victim "walk it off."

**7. What to tell the ambulance:**
- Voltage if known (mains 220V, generator, three-phase, overhead).
- Duration of contact.
- Time of incident.
- Loss of consciousness — yes/no, duration.
- Burns — location, approximate size.
- Any other injuries.

**8. After arrival at the hospital:**
- They will check ECG (cardiac rhythm monitoring for several hours).
- Blood tests for muscle breakdown (CK levels).
- Urine output monitoring (rhabdomyolysis indicator).

**Helplines:** 115, 1122, KE 118, WAPDA 118.

⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For serious injuries or medical emergencies, call **115** or **1122** immediately. Do not attempt procedures beyond your training.
""",
        searchable_text="electric shock during assessment cpr abc airway breathing circulation burns falls hospital pakistan",
        sources=[PRCS, AHA],
        disclaimer=True,
    ),
    _entry(
        id="electric_shock.after.001",
        disaster_type="electric_shock",
        phase="after",
        title="After an electric shock — follow-up and prevention",
        content="""
**Even after ER discharge, electric-shock recovery extends for days to weeks.**

**1. ER follow-up:**
- Most patients are observed for several hours after a low-voltage shock; for high-voltage, 24+ hours.
- Discharge instructions typically cover: signs of cardiac arrhythmia (palpitations, chest pain, fainting), kidney problems (low urine output, dark urine), and burn care.
- Follow up with a cardiologist if arrhythmia was detected.
- Get a structured ECG follow-up at 24 and 72 hours if symptoms persist.

**2. Burn care:**
- Electrical burns often look small at the entry/exit points but tunnel through tissue. Some require surgical debridement weeks later.
- Daily wound check. See a doctor if redness expands, pus develops, or you spike a fever.
- Tetanus booster if not current.

**3. Source investigation — don't re-energise without it:**
- Have an electrician find what caused the shock. The same fault has caused fatalities elsewhere.
- Common findings: corroded earthing, faulty appliance, illegal joint, kacha extension.
- Replace and re-test before turning power back on.

**4. WAPDA / KE / LESCO complaint:**
- If the shock came from a streetlight pole, downed line, or municipal transformer, file a complaint (118 for WAPDA / KE).
- Follow up in writing — verbal complaints are easy to lose.

**5. Mental health follow-up:**
- Electric-shock survivors often report sleep disruption, anxiety around electrical appliances, and intrusive memories. These usually fade in 2–4 weeks.
- If symptoms worsen or persist, call Rozan (0304-111-1741) or Umang (0311-7786264).

**6. Prevention going forward:**
- Install RCD / ELCB / GFCI on the bathroom and outdoor circuits.
- Replace kacha extensions throughout the house.
- Inspect monsoon-vulnerable wiring.

**Helplines:** 115, 1122, 118 (WAPDA / KE).
""",
        searchable_text="electric shock after aftermath ecg cardiac burn rcd elcb gfci wapda follow up pakistan mental health",
        sources=[PRCS, WHO],
    ),

    # ── Mental health (5 entries; existing one reclassified separately) ──
    _entry(
        id="mental_health.during.children.001",
        disaster_type="mental_health",
        phase="during",
        title="Helping children process disaster trauma",
        content="""
**Children are not small adults. Their reactions to disaster look different — and what helps adults often doesn't help children.**

**Common reactions in the first weeks (and what they look like):**
- **Regression:** bedwetting, thumb-sucking, baby talk in older children.
- **Clinginess:** following parents room-to-room, refusing to sleep alone.
- **School refusal:** stomachaches on school mornings, refusing to leave the house.
- **Nightmares and sleep disruption.**
- **Aggressive play, drawing the disaster repeatedly** — this is processing, not pathology, when it gradually decreases.
- **Quiet withdrawal** — sometimes harder to spot than tantrums but equally serious.
- **Physical complaints** — headaches, stomach pain without medical cause.
- **Hypervigilance** — flinching at loud noises, asking repeatedly if it will happen again.

**What helps:**
- **Routine.** Same wake time, same bedtime, same meal times. Routine signals to the brain that the world is predictable again.
- **Physical reassurance.** Hugs. Sitting close. Holding hands during conversation. Younger children especially need touch.
- **Honest, age-appropriate language.** Don't say "everything is fine" if it isn't. Do say "we're safe right now and I'm here."
- **Limit news and disaster footage.** Especially graphic content. Re-traumatising.
- **Let them talk or draw.** Don't push, don't dismiss. "I see you drew the building falling. Tell me about it" is better than "don't think about that."
- **Maintain school attendance.** If possible. School is a normalising structure. Tell the teacher what's happening so they can support, not push.
- **One-on-one time.** 15 minutes a day where the parent is not on a phone, just present.

**When to seek professional help:**
- Symptoms that worsen rather than ease in 4–6 weeks.
- Self-harm or suicide talk — call 115 immediately or take to a hospital ER.
- Refusal to eat, severe weight loss.
- Inability to function — can't go to school, can't sleep at all, can't be left alone.
- Aggressive behaviour that endangers themselves or others.

**Free counseling resources (Pakistan):**
- **Rozan Counseling Helpline** — 0304-111-1741 (psychosocial, child protection).
- **Umang** — 0311-7786264 (24/7 mental health helpline).
- **Madadgar Child Helpline** — 1098 (child protection, abuse).
- District psychiatric departments at DHQ hospitals.

⚠️ **Note:** This is supportive guidance, not medical treatment. Severe or persistent issues need a qualified mental health professional.
""",
        searchable_text="mental health children disaster trauma kids regression nightmares school routine madadgar rozan umang pakistan",
        sources=[WHO, ROZAN, UMANG],
        disclaimer=True,
    ),
    _entry(
        id="mental_health.during.guilt.001",
        disaster_type="mental_health",
        phase="during",
        title="Survivor's guilt and disaster-related shame",
        content="""
**"Why me? Why did I survive when they didn't?" Survivor's guilt is one of the most common and least-discussed reactions to a disaster.**

**What it can look like:**
- Persistent thoughts of "I should have done more / I should have saved them."
- Intrusive memories focused on the moment of survival vs the moment of others' deaths.
- Difficulty enjoying anything — eating, sleeping, family time — because "they can't."
- Avoiding people, places, or topics that remind you of the event.
- A flat, numb feeling rather than active grief.
- Sometimes self-punishing behaviour — overworking, refusing rest, refusing help.

**What helps (and what doesn't):**

**Helps:**
- **Speak it.** Survivor's guilt is famously private. Naming it to a trusted person breaks part of its hold.
- **A simple cognitive reframe:** survival is not a fault. The things that decided who lived and died were rarely under any individual's control. The earthquake didn't choose. The flood didn't choose.
- **Channel into action — but only if it's the right time.** Helping others (Edhi, Chhipa, Pakistan Red Crescent volunteer work, blood donation) gives a sense of purpose. But early on, rest matters more.
- **Religious / spiritual practices** — for many Pakistanis, prayer, dua, going to the mosque/church/mandir/gurdwara is part of meaning-making. If it helps, use it.
- **Professional support.** Trauma-focused therapy is effective. Several Pakistan psychologists (Pakistan Psychological Association directory) offer trauma-specific care.

**Doesn't help:**
- "Move on, others have it worse." Comparative suffering is not a healing tool.
- Numbing with alcohol, paan, gutka, sleeping pills without medical supervision.
- Endless rehearsal of the event alone, without an outlet.

**When to seek professional help:**
- Suicidal thoughts. Even fleeting ones. Call 115 immediately.
- Self-harm.
- Inability to function for more than 4–6 weeks.
- Increasing rather than decreasing intensity of symptoms.
- Substance use to cope.
- Severe sleep disruption (less than 4 hours/night for more than a week).

**Free counseling lines:**
- **Rozan Counseling Helpline** — 0304-111-1741.
- **Umang** — 0311-7786264 (24/7).
- **Taskeen** — taskeen.org (online resources).
- DHQ psychiatry departments are free emergency referrals.

⚠️ **Note:** This is supportive guidance, not medical treatment.
""",
        searchable_text="mental health survivors guilt shame disaster trauma reframe rozan umang taskeen pakistan",
        sources=[WHO, ROZAN],
        disclaimer=True,
    ),
    _entry(
        id="mental_health.during.red_flags.001",
        disaster_type="mental_health",
        phase="during",
        title="Mental health red flags — when to seek professional help",
        content="""
**Most people recover from a disaster's psychological impact in weeks. A minority don't, and the gap between "this is normal" and "this needs help" is the most useful thing to know.**

**It's normal to have, in the first 3–4 weeks:**
- Sleep disruption, vivid dreams.
- Hypervigilance — flinching at sounds, scanning rooms.
- Intrusive memories that come and go.
- Anxiety, irritability, anger.
- Difficulty concentrating.
- Mood swings.
- Avoidance of disaster-related places or topics.
- Numbness alternating with strong emotion.

**These usually ease as routine returns and time passes.**

**Red flags — get professional help:**

**Acute (call 115 / nearest ER immediately):**
- Suicidal thoughts, plans, or attempts.
- Self-harm.
- Hallucinations (seeing or hearing things others don't).
- Severe dissociation (feeling unreal, disconnected from body for hours).
- Plans to harm someone else.

**Subacute (this week, not "someday"):**
- Symptoms worsen rather than ease after 4 weeks.
- Inability to function — can't work, can't care for children, can't leave bed.
- Sleep less than 4 hours per night for more than a week.
- Substance use to cope (alcohol, sedatives, paan/gutka, prescription drug abuse).
- Severe panic attacks several times a week.
- Persistent intrusive memories that disrupt daily activity.
- Self-isolating from family — refusing meals, not speaking.
- New onset depression — pervasive low mood, loss of pleasure in everything.

**For children, additional red flags:**
- Self-harm.
- Talking about death, "going away," "joining" deceased relatives.
- Severe regression that doesn't resolve.
- Refusing to eat.
- Dramatic personality change.

**Where to go:**
- **Rozan Counseling Helpline** — 0304-111-1741.
- **Umang** — 0311-7786264 (24/7, but explicitly NOT for active suicidal cases — for those, 115).
- **Taskeen** — taskeen.org (online resources, Pakistan Psychological Association directory).
- **Government hospitals** — psychiatry departments at AKUH, JPMC, Mayo, PIMS, LRH, KTH.
- **Pakistan Psychological Association directory** for paid private psychologists.
- **District Health Officer** — every district has at least one mental-health staff position.

**A note on stigma:** seeking mental health support after a disaster is treatment, not weakness. The 2005 Kashmir quake, 2010 and 2022 floods all left documented mental health tails that benefited from professional care.

⚠️ **Note:** This is supportive guidance. Active crises need immediate professional intervention.
""",
        searchable_text="mental health red flags warnings professional help suicide self harm depression rozan umang taskeen pakistan",
        sources=[WHO, ROZAN, UMANG],
        disclaimer=True,
    ),
    _entry(
        id="mental_health.during.grief.001",
        disaster_type="mental_health",
        phase="during",
        title="Grief after disaster — supporting yourself and others",
        content="""
**Disaster grief is different from other grief — it can be sudden, public, and tangled with logistical chaos. Grieving in the middle of a relief operation is its own challenge.**

**The early hours and days:**
- Shock and numbness are normal. People often describe feeling "outside themselves" for the first 24–72 hours.
- Reflexive caretaking ("I have to be strong for the children") is common — and usually means grief delayed, not avoided.
- Eat and drink even when you don't want to. Dehydration and low blood sugar make grief physically harder.
- Sleep when you can. Don't medicate yourself into sleep without a doctor.

**The first weeks:**
- Waves of grief — strong emotion alternating with quiet — are how grief moves. There is no order.
- Anger, including anger at the deceased, at God, at responders, at yourself, is a normal grief emotion. It is not disrespectful.
- Crying or not crying are both fine. Some people grieve quietly.
- Cultural and religious practices — janazah, soyem, chaliswan, dua, prayer, going to the qabristan — are part of how Pakistanis grieve. Use what feels right.

**Practical support for the bereaved:**

**Help with logistics, not philosophy.**
- Bring food. Keep a thermos of water near them.
- Take over the phone for a few hours so they can rest.
- Help with paperwork (death certificate, insurance, BISP).
- Take the children for an afternoon.

**What to say:**
- "I'm so sorry. I'm here."
- "I don't know what to say but I'm not going anywhere."
- "Tell me about them" (when the bereaved is ready).

**What NOT to say:**
- "Everything happens for a reason." (Pakistanis hear this a lot. It mostly hurts.)
- "Be strong for the children."
- "At least…" (any sentence that starts this way).
- "It was their time." (Don't impose your theology on someone else's grief.)
- "You'll get over it."

**Anniversaries and reminders:**
- The Eid that was their last Eid. Their birthday. The disaster anniversary. These dates remain hard for years.
- Acknowledge them. A short message means a lot.

**When grief becomes complicated grief (warrants professional help):**
- After 6 months: persistent intense yearning that prevents daily function.
- Inability to accept the loss, even months later.
- Severe withdrawal, refusal to engage.
- Self-harm or suicidal thoughts.
- Inability to work, parent, or care for self.

**Free counseling support:**
- **Rozan Counseling Helpline** — 0304-111-1741.
- **Umang** — 0311-7786264.
- Religious leaders, when trusted, can also offer pastoral support.

⚠️ **Note:** This is supportive guidance. If you are in crisis, please call 115 immediately.
""",
        searchable_text="mental health grief disaster bereavement loss janazah complicated grief support rozan umang pakistan",
        sources=[WHO, ROZAN],
        disclaimer=True,
    ),

    # ── First aid (+5: hypothermia, diabetic, seizure, anaphylaxis, wound infection) ──
    _entry(
        id="first_aid.during.hypothermia.001",
        disaster_type="general",
        phase="during",
        topic="first_aid",
        title="First aid — hypothermia (cold injury)",
        content="""
⚠️ **For severe cold injury or anyone who is not responding normally, call 115 or 1122 immediately.**

**Where it happens in Pakistan:**
- GB, AJK, northern KPK winters: Skardu, Hunza, Chitral, Murree, Naran-Kaghan, Galyat.
- High-altitude trekking, snowstorm-stranded vehicles.
- Flood victims who spend hours in cold water.
- Homeless individuals during winter cold snaps in Punjab and KPK.

**Recognise hypothermia:**

**Mild (35–32°C body temperature):**
- Persistent shivering.
- Cold, pale skin.
- Slowed responses, mumbled speech, clumsy hands.
- Confusion that comes and goes.

**Moderate to severe (below 32°C):**
- Shivering may stop (a dangerous sign).
- Severe confusion, disorientation.
- Drowsiness, unconsciousness.
- Slow, weak, irregular pulse.
- Slow breathing.
- Stiff muscles. Possibly "paradoxical undressing" — patient strips clothing.

**First aid:**

**1. Get them out of the cold.** Move to shelter. If shelter isn't available, build a barrier from wind (rocks, snow wall, vehicle).

**2. Remove wet clothing.** Replace with dry layers. If no dry clothing, wring out wet clothes and put back on as a partial barrier.

**3. Insulate from the ground.** Cold ground draws heat fast. Sleeping bag, blankets, even backpacks under the body.

**4. Re-warm gradually.**
- Cover head, neck, torso, and groin first — these are the heat-loss centres.
- Skin-to-skin contact under blankets is highly effective if a willing helper is available.
- Warm sweet drinks if conscious and able to swallow safely.
- DO NOT use hot water bottles directly on cold skin (burn risk on numb skin).
- DO NOT submerge in hot water — cardiac arrest risk.

**5. Handle gently.** Severe hypothermia patients can have arrhythmias triggered by rough movement.

**6. Watch breathing.** If absent or only gasping → CPR. Continue much longer than usual; "they're not dead until they're warm and dead" is the EM mantra.

**Do NOT:**
- Give alcohol. It makes hypothermia much worse.
- Massage / rub limbs.
- Apply direct intense heat (heater, fire, hot water bath).
- Allow the patient to walk if severely affected — exertion can cause collapse.

**For frostbite (numb white/grey patches on extremities):**
- Get to shelter.
- Re-warm in warm (not hot) water (37–39°C).
- Don't rub. Don't refreeze (which is worse than leaving it frozen until you can re-warm permanently).
- ER review even after re-warming — tissue damage is often invisible.

**Helplines:** 115, 1122. Call them especially if the patient is unconscious, very young, very old, or stranded outdoors.

⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For serious injuries or medical emergencies, call **115** or **1122** immediately. Do not attempt procedures beyond your training.
""",
        searchable_text="first aid hypothermia cold winter gilgit ajk frostbite shivering re-warming pakistan flood snowstorm",
        sources=[WHO, RED_CROSS_FA],
        disclaimer=True,
    ),
    _entry(
        id="first_aid.during.diabetic_emergency.001",
        disaster_type="general",
        phase="during",
        topic="first_aid",
        title="First aid — diabetic emergency (low blood sugar)",
        content="""
⚠️ **If unsure whether someone's blood sugar is high or low, treat as low — too low is acutely life-threatening; too high evolves over hours.**

**Pakistani context:** Type 2 diabetes is widespread. Hypoglycaemia (low blood sugar) is more often a first-aid emergency than hyperglycaemia.

**Hypoglycaemia (low blood sugar) — the acute first-aid emergency:**

Recognise:
- Sudden onset shakiness, sweating, pale skin.
- Confusion, slurred speech, irritability.
- Hunger, weakness.
- Rapid heartbeat.
- In severe cases: seizures, loss of consciousness.
- Trigger often: missed meal, extra exercise, alcohol, or insulin/medication overdose.

**If conscious and able to swallow:**

**1. Sugar fast.** Give:
- 15 g of fast-acting sugar — 3 teaspoons of sugar in water, half a glass of fruit juice, 4–5 dates, 3 glucose tablets, or one tablespoon of honey.
- NOT chocolate / paan / nuts initially — fat slows absorption.

**2. Wait 15 minutes. Recheck.** If still symptomatic, repeat the 15 g of sugar.

**3. Once stabilised:** give a longer-acting carbohydrate — roti, paratha, biscuit with milk — so they don't crash again.

**If unconscious or unable to swallow:**

**1. DO NOT put food or liquid in their mouth.** Aspiration / choking risk.

**2. Call 115 / 1122 immediately.**

**3. Place in recovery position (on side).**

**4. If a glucagon kit is available** (some diabetic patients carry one), follow the package instructions. This is an injection and works without swallowing.

**5. Stay until paramedics arrive.**

**Hyperglycaemia (high blood sugar):**

Comes on slowly over hours/days:
- Excessive thirst, frequent urination.
- Fruity breath (acetone smell).
- Fatigue, nausea, vomiting.
- Deep rapid breathing.
- Confusion progressing to coma in severe DKA (diabetic ketoacidosis).

If suspected: call ambulance, encourage water intake if conscious, do NOT give insulin yourself.

**General principles for any diabetic emergency:**
- Check for medical ID bracelets.
- Note medications (insulin name, dose, last dose time) for the ambulance team.
- Sugar bracelets / candy in the bedside drawer is a low-tech intervention that has saved lives.

**Helplines:** 115, 1122, nearest hospital.

⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For serious injuries or medical emergencies, call **115** or **1122** immediately. Do not attempt procedures beyond your training.
""",
        searchable_text="first aid diabetic emergency hypoglycaemia low blood sugar insulin dates juice glucagon dka pakistan",
        sources=[WHO, AHA],
        disclaimer=True,
    ),
    _entry(
        id="first_aid.during.seizure.001",
        disaster_type="general",
        phase="during",
        topic="first_aid",
        title="First aid — seizure response",
        content="""
⚠️ **Most seizures stop on their own within 1–3 minutes. Call 115 or 1122 if it lasts longer than 5 minutes, repeats, or the person doesn't fully recover.**

**Recognise a seizure:**
- Sudden loss of consciousness.
- Generalised stiffening followed by rhythmic jerking of limbs.
- Possibly biting tongue, drooling, brief loss of bladder control.
- Eyes may roll back; breathing may pause briefly.
- Some seizures are subtle: blank stare, lip smacking, repetitive movements with no response — also need attention.

**During the seizure — DO:**

**1. Time it.** Look at the clock the moment it starts.

**2. Protect from injury.** Move sharp objects, furniture corners, hot drinks away. Cushion the head with something soft (rolled cloth, jacket).

**3. Loosen tight clothing** around the neck.

**4. Roll onto the side** if you can do so safely without forcing — this lets saliva drain and protects the airway. If they're stiff, just protect the head and wait for the jerking to stop.

**5. Stay with them.** Talk calmly. Don't leave them alone.

**During the seizure — DO NOT:**

- **Do NOT put anything in the mouth.** No spoon, no wallet, no fingers. The "swallowing the tongue" myth has caused broken teeth and bitten rescuers.
- Do NOT restrain limbs. Hold the head softly to prevent floor injury, but don't pin arms / legs.
- Do NOT splash water on them or try to "wake them up."
- Do NOT give food or water until they are fully alert.

**After the seizure — postictal phase (5–30 minutes):**
- Confusion, drowsiness, slow speech are normal.
- Place in recovery position.
- Stay with them. Reassure quietly.
- Don't give them anything to eat or drink until they're fully alert.
- Note what happened — limb jerking pattern, duration, eye direction, biting / incontinence — this matters to the doctor.

**Call 115 / 1122 if:**
- It's their first seizure.
- It lasts longer than 5 minutes.
- They have a second seizure without recovering between.
- They're injured during the seizure.
- They're pregnant.
- It happened in water.
- They have diabetes (could be hypoglycaemia mimicking seizure).
- They don't return to normal within 30 minutes.

**For repeated seizures (status epilepticus):** sustained or recurring seizures are a true emergency. Lasting brain injury starts after about 30 minutes of continuous seizure activity. Get to a hospital immediately.

**For known epilepsy patients:**
- Some carry an emergency med (rectal diazepam / midazolam) — follow the family / patient's emergency plan.
- A medical ID bracelet helps responders.

**Helplines:** 115, 1122.

⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For serious injuries or medical emergencies, call **115** or **1122** immediately. Do not attempt procedures beyond your training.
""",
        searchable_text="first aid seizure epilepsy convulsion postictal status epilepticus pakistan emergency",
        sources=[WHO, RED_CROSS_FA],
        disclaimer=True,
    ),
    _entry(
        id="first_aid.during.anaphylaxis.001",
        disaster_type="general",
        phase="during",
        topic="first_aid",
        title="First aid — anaphylaxis (severe allergic reaction)",
        content="""
⚠️ **Anaphylaxis is a true emergency. If suspected: call 115 / 1122 IMMEDIATELY, give epinephrine if available, lay flat, watch breathing.**

**Recognise anaphylaxis (rapid onset, usually within minutes of exposure):**

**Skin:**
- Widespread hives, itching, flushing.
- Swelling of face, lips, tongue, throat.

**Breathing:**
- Wheezing, shortness of breath.
- Hoarse voice, tight throat, difficulty swallowing.
- Stridor (high-pitched noise on inhalation) — particularly dangerous.

**Circulation:**
- Rapid weak pulse.
- Pallor, sweating.
- Dizziness, lightheadedness.
- Loss of consciousness.

**Other:**
- Nausea, vomiting, abdominal cramps, diarrhoea.
- Sense of impending doom (patient may say "I feel like I'm going to die").

**Common Pakistani triggers:**
- Wasp / hornet / honeybee stings (especially common in summer in northern areas).
- Certain antibiotics (penicillin family) — frequently the trigger in Pakistani healthcare settings.
- Peanuts, tree nuts, seafood.
- Latex (gloves, balloons in older formulations).

**First aid:**

**1. CALL 115 or 1122 IMMEDIATELY.** Don't wait. Anaphylaxis can kill in 15–30 minutes.

**2. Epinephrine (adrenaline auto-injector) if available:**
- EpiPen / Auvi-Q / similar — inject into the outer thigh, hold for 10 seconds.
- Through clothing is fine in an emergency.
- A second dose can be given after 5–15 minutes if symptoms don't improve.
- Note the time of injection — paramedics need to know.

**3. Position:**
- Lie flat with legs raised (helps blood return to the heart).
- If breathing is severely impaired, sit them up slightly.
- If unconscious but breathing, recovery position.
- Pregnant patients: lie on left side.

**4. Loosen tight clothing.**

**5. If known cause is still in contact** (insect stinger embedded, food still in mouth):
- Stinger: scrape off with a credit card edge. Don't squeeze — squeezes more venom in.
- Food: rinse mouth with water if conscious; don't induce vomiting.

**6. CPR if the heart stops.** Continue until paramedics arrive.

**Watch for biphasic reaction:** symptoms can come back hours after they initially improve. Anaphylaxis patients need ER observation for at least 6 hours, ideally overnight, even if they seem fine after the first dose.

**Pakistani healthcare context:**
- Many smaller hospitals stock adrenaline ampoules but not auto-injectors. ER staff will give IM adrenaline.
- Some patients with known severe allergies carry pre-filled syringes — check the bag/wallet.
- Patients with prior episodes should have a written emergency action plan.

**Prevention going forward:**
- Identify the trigger via allergist (skin test or specific IgE blood test).
- Carry an auto-injector if prescribed.
- Medical ID bracelet listing the allergy.
- Avoid the trigger; teach family/colleagues to recognise symptoms.

**Helplines:** 115, 1122.

⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For serious injuries or medical emergencies, call **115** or **1122** immediately. Do not attempt procedures beyond your training.
""",
        searchable_text="first aid anaphylaxis allergic reaction epinephrine epipen wasp bee penicillin peanut food allergy pakistan",
        sources=[WHO, AHA],
        disclaimer=True,
    ),
    _entry(
        id="first_aid.during.wound_infection.001",
        disaster_type="general",
        phase="during",
        topic="first_aid",
        title="First aid — wound care and infection prevention",
        content="""
**Most disaster wounds — flood cuts, post-quake debris injuries, road-accident scrapes — get infected because they're contaminated. Good wound care in the first 24 hours prevents most of those infections.**

**Initial care (within minutes to hours):**

**1. Stop bleeding first.** Direct pressure with a clean cloth. See the bleeding-control card for severe bleeds.

**2. Wash your hands** before touching the wound. Soap + clean water. If no clean water, use alcohol-based sanitiser.

**3. Irrigate the wound.** This is the single most important infection-prevention step.
- Clean (drinking-quality) water under moderate pressure for at least 1–2 minutes.
- A syringe without needle, a squeeze bottle, or a clean plastic bag with a small hole all work.
- Don't pour antiseptic into a deep wound — it irritates tissue. Wash with water; antiseptic on the edges only.

**4. Remove visible debris with clean tweezers** (clean = washed with soap and water and rinsed). Don't dig for embedded objects — that's an ER job.

**5. Apply a clean dressing.** Sterile gauze ideally; a clean cotton cloth if not.

**6. Tetanus.** Any wound is a tetanus risk in Pakistan. If your last booster is more than 5 years ago, OR you can't remember, OR the wound is deep/dirty, get a tetanus shot at the nearest BHU / RHC / DHQ within 24 hours.

**Watch for infection (24–72 hours):**

Signs:
- Redness expanding from the wound edge.
- Increasing pain (not decreasing).
- Swelling.
- Warmth around the wound.
- Pus or yellow/green discharge.
- Bad smell.
- Red streaks running from the wound up the limb.
- Fever.
- Swollen lymph nodes near the wound.

**If any of these:** see a doctor same-day. Antibiotics may be needed.

**Daily wound care until healed:**
- Once daily wash with clean water and mild soap.
- Pat dry (don't rub).
- Apply a thin layer of antibiotic ointment if available (Bactroban, Fucidin, Polyfax — all available at Pakistani pharmacies).
- Fresh dressing.
- Watch for signs of infection.

**For specific wound types:**

**Animal bites (dog, cat, rat — common after floods):**
- Wash thoroughly for 15 minutes.
- See a hospital. Rabies is endemic in Pakistan — anti-rabies vaccine is required. Call NIH (National Institute of Health) for guidance.
- Tetanus booster.

**Snake bite:** see the snake-bite first aid card. Wound care is secondary to anti-venom.

**Burns:** see the burns first aid card. Wound care is different.

**Puncture wounds (nail, glass):**
- Hard to clean fully. Get medical evaluation.
- Higher infection risk.

**Wounds contaminated with flood water:**
- Wash thoroughly.
- See a doctor — flood water carries cholera, leptospirosis, and other pathogens.

**Helplines:** 115, 1122, nearest BHU / RHC / DHQ for tetanus.

⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For serious injuries or medical emergencies, call **115** or **1122** immediately. Do not attempt procedures beyond your training.
""",
        searchable_text="first aid wound infection irrigation tetanus rabies dog bite flood pakistan antibiotic dressing care",
        sources=[WHO, RED_CROSS_FA, PRCS],
        disclaimer=True,
    ),
]


# ─── Reclassifications ────────────────────────────────────────────────────────
def reclassify(entries: list[dict]) -> int:
    """Apply Phase 2 reclassifications. Returns number of entries changed."""
    changed = 0
    for e in entries:
        if e.get("id") == "mental_health_post_disaster_1":
            # Was disaster_type=general, topic=first_aid. Reclassify to
            # mental_health and drop the topic facet (not a first-aid entry).
            if e.get("disaster_type") != "mental_health" or e.get("topic"):
                e["disaster_type"] = "mental_health"
                e.pop("topic", None)
                e["last_verified"] = TODAY
                changed += 1
        elif e.get("id") == "cyclone_1":
            # Was phase=general; the content describes during-cyclone protocol.
            if e.get("phase") != "during":
                e["phase"] = "during"
                changed += 1
    return changed


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    kb_path = repo_root / "data" / "knowledge_base.json"

    with kb_path.open("r", encoding="utf-8") as f:
        kb = json.load(f)

    if kb.get("version") != "2.0.0":
        print("KB is not v2; run migrate_kb_v1_to_v2.py first.", file=sys.stderr)
        return 2

    entries = kb["entries"]
    existing_ids = {e["id"] for e in entries}

    reclassified = reclassify(entries)

    appended = 0
    for new in NEW_ENTRIES:
        if new["id"] in existing_ids:
            continue
        entries.append(new)
        existing_ids.add(new["id"])
        appended += 1

    kb["updated_at"] = TODAY

    with kb_path.open("w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        f"Reclassified {reclassified} existing entries; "
        f"appended {appended} new entries. Total now: {len(entries)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
