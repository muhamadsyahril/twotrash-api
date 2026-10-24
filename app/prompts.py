QUESTION = "Which waste bin should the main item shown in `photo` go into?"

CRITERIA = {
    "organic": (
        "Biodegradable organic waste: food scraps, fruit or vegetable peels, "
        "leaves, flowers, twigs, eggshells, bones, coffee grounds, tea leaves."
    ),
    "anorganic": (
        "Non-biodegradable or recyclable waste: plastic bottles, plastic bags, "
        "food wrappers, styrofoam, cans, metal, glass, paper, cardboard, rubber."
    ),
    "other": (
        "Hazardous or residual waste, or nothing recognizable: batteries, "
        "electronics, light bulbs, medicine, masks, diapers, tissues, mixed "
        "items, or an empty or unclear image."
    ),
}

SUMOPOD_SYSTEM_PROMPT = (
    "You classify waste from a photo into exactly one category.\n"
    + "\n".join(f"- {name}: {desc}" for name, desc in CRITERIA.items())
    + '\nReply with JSON only: {"category": "organic" | "anorganic" | "other"}'
)
