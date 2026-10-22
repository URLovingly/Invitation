"""Single source of truth for the three pricing options."""

FEATURES = (
    "whatsapp_generator",
    "rsvp_dashboard",
    "multi_day_routing",
    "upi_shagun",
    "custom_audio",
)

FEATURE_LABELS = {
    "whatsapp_generator": "WhatsApp message generator",
    "rsvp_dashboard": "Live RSVP dashboard",
    "multi_day_routing": "Multi-day selective event routing",
    "upi_shagun": "UPI Shagun integration",
    "custom_audio": "Custom background audio",
}

PLANS = {
    "free": {
        "id": "free",
        "name": "Free Tier (Trial)",
        "price_paise": 0,
        "link_limit": 5,
        "hosting_days": 7,
        "features": [],
        "highlights": ["Up to 5 personalized guest links", "7 days of link hosting", "All invitation designs"],
        "sort_order": 1,
    },
    "standard": {
        "id": "standard",
        "name": "Standard Celebration",
        "price_paise": 99900,
        "link_limit": 100,
        "hosting_days": 180,
        "features": ["whatsapp_generator", "rsvp_dashboard"],
        "highlights": [
            "Up to 100 personalized guest links",
            "WhatsApp message generator",
            "Live RSVP dashboard",
            "6 months of link hosting",
        ],
        "sort_order": 2,
    },
    "grand": {
        "id": "grand",
        "name": "Grand Celebration",
        "price_paise": 249900,
        "link_limit": 500,
        "hosting_days": 365,
        "features": list(FEATURES),
        "highlights": [
            "Up to 500 personalized guest links",
            "Multi-day selective event routing",
            "UPI Shagun integration",
            "Custom background audio",
            "1 year of link hosting",
            "Everything in Standard",
        ],
        "sort_order": 3,
    },
}


def get_plan(plan_id):
    return PLANS.get(plan_id)


def plan_has(plan_id, feature):
    plan = PLANS.get(plan_id)
    return bool(plan) and feature in plan["features"]


def cheapest_plan_with(feature):
    for plan in sorted(PLANS.values(), key=lambda p: p["sort_order"]):
        if feature in plan["features"]:
            return plan["id"]
    return None


def public_plan(plan):
    return {
        "id": plan["id"],
        "name": plan["name"],
        "price_rupees": plan["price_paise"] // 100,
        "price_paise": plan["price_paise"],
        "link_limit": plan["link_limit"],
        "hosting_days": plan["hosting_days"],
        "features": list(plan["features"]),
        "highlights": list(plan["highlights"]),
    }


def seed_plans(db):
    for plan in PLANS.values():
        flags = {name: int(name in plan["features"]) for name in FEATURES}
        db.execute(
            """INSERT INTO plans (id, name, price_paise, link_limit, hosting_days,
                                  whatsapp_generator, rsvp_dashboard, multi_day_routing,
                                  upi_shagun, custom_audio, sort_order)
               VALUES (:id, :name, :price_paise, :link_limit, :hosting_days,
                       :whatsapp_generator, :rsvp_dashboard, :multi_day_routing,
                       :upi_shagun, :custom_audio, :sort_order)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, price_paise=excluded.price_paise,
                 link_limit=excluded.link_limit, hosting_days=excluded.hosting_days,
                 whatsapp_generator=excluded.whatsapp_generator,
                 rsvp_dashboard=excluded.rsvp_dashboard,
                 multi_day_routing=excluded.multi_day_routing,
                 upi_shagun=excluded.upi_shagun, custom_audio=excluded.custom_audio,
                 sort_order=excluded.sort_order""",
            {**{k: plan[k] for k in ("id", "name", "price_paise", "link_limit", "hosting_days", "sort_order")}, **flags},
        )
