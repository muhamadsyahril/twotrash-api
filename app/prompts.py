# Item slug -> kategori (organic | anorganic | other)
ITEM_CATEGORY = {
    # Organik
    "kulit_pisang": "organic",
    "sisa_nasi": "organic",
    "sisa_sayur": "organic",
    "kulit_buah": "organic",
    "daun": "organic",
    "ampas_kopi": "organic",
    "ampas_teh": "organic",
    "cangkang_telur": "organic",
    "tulang": "organic",
    # Nonorganik / anorganic
    "botol": "anorganic",
    "kaleng_minuman": "anorganic",
    "gelas_plastik": "anorganic",
    "kantong_plastik": "anorganic",
    "tutup_botol": "anorganic",
    "kertas": "anorganic",
    "kardus": "anorganic",
    "sedotan": "anorganic",
    # Lainnya
    "tisu": "other",
    "popok": "other",
    "masker": "other",
    "puntung_rokok": "other",
    "styrofoam": "other",
    "sampah_campuran": "other",
}

# Deskripsi Choice untuk Jev / prompt Sumopod
ITEM_CRITERIA = {
    "kulit_pisang": "Banana peel.",
    "sisa_nasi": "Leftover cooked rice.",
    "sisa_sayur": "Leftover cooked or raw vegetables.",
    "kulit_buah": "Fruit peel that is not a banana peel (orange, apple, mango, etc.).",
    "daun": "Leaves, twigs, or garden green waste.",
    "ampas_kopi": "Used coffee grounds or coffee filter pulp.",
    "ampas_teh": "Used tea leaves or tea bag contents.",
    "cangkang_telur": "Eggshells.",
    "tulang": "Animal bones or fish bones.",
    "botol": "Plastic or glass drink bottle (not the bottle cap alone).",
    "kaleng_minuman": (
        "Aluminum or metal beverage can (soda, soft drink, energy drink). "
        'Also choose this if the photo or any visible text says '
        '"sampah kaleng minuman", "kaleng minuman", or similar label.'
    ),
    "gelas_plastik": "Disposable plastic cup or plastic tumbler.",
    "kantong_plastik": "Plastic bag or plastic shopping bag.",
    "tutup_botol": "Bottle cap alone (plastic or metal), not the whole bottle.",
    "kertas": "Paper scrap, notebook paper, or newspaper (not cardboard).",
    "kardus": "Cardboard box or corrugated cardboard.",
    "sedotan": "Drinking straw (plastic or paper).",
    "tisu": "Tissue paper, wet wipe, or napkin used as tissue.",
    "popok": "Diaper or sanitary pad.",
    "masker": "Face mask (medical or cloth).",
    "puntung_rokok": "Cigarette butt or ash with cigarette remains.",
    "styrofoam": "Styrofoam / polystyrene food container or packing foam.",
    "sampah_campuran": (
        "Mixed trash, unrecognizable waste, empty/unclear image, "
        "or anything that does not match the other options."
    ),
}

QUESTION = (
    "What is the main waste item shown in `photo`? "
    "If visible text labels the waste (for example 'sampah kaleng minuman'), "
    "use that label to choose the matching item."
)

SUMOPOD_SYSTEM_PROMPT = (
    "You classify waste from a photo into exactly one item slug.\n"
    "Items and bins:\n"
    + "\n".join(
        f"- {item} ({ITEM_CATEGORY[item]}): {desc}"
        for item, desc in ITEM_CRITERIA.items()
    )
    + "\nIf text in the photo says 'sampah kaleng minuman' or 'kaleng minuman', "
    "choose kaleng_minuman.\n"
    'Reply with JSON only: {"item": "<slug>", "category": "organic"|"anorganic"|"other"}'
)
