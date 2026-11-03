"""The tag set for FR-5: one label per field, taken from the PRD and the UI spec's charts.

Every field has an "unknown" label (not_stated or none) that the model omits; missing
fields are filled with it when tags are stored, so counts always have a "not stated" bucket.
"""
from __future__ import annotations

FIELDS: dict[str, dict] = {
    "stage": {
        "unknown": "not_stated",
        "help": "where the writer is in their SIP journey",
        "labels": {
            "before_starting": "deciding whether or how to start",
            "onboarding": "setting up the account, KYC, mandate or first SIP",
            "first_instalment": "the first instalment or first month",
            "months_2_6": "2 to 6 months in",
            "months_7_12": "7 to 12 months in",
            "after_year_1": "more than a year in",
        },
    },
    "event": {
        "unknown": "not_stated",
        "help": "what the writer did or is about to do with a SIP",
        "labels": {
            "started": "started a SIP", "continued": "kept going despite something",
            "paused": "paused a SIP", "reduced": "reduced the amount", "stopped": "stopped or cancelled a SIP",
            "considering_stopping": "thinking about stopping or pausing",
        },
    },
    "trigger": {
        "unknown": "not_stated",
        "help": "what prompted that event or decision",
        "labels": {
            "switching_platform_or_plan": "moving to another app, AMC or direct plan",
            "goal_or_wealth": "a goal, wealth building or retirement",
            "market_fall_or_losses": "a market fall or seeing losses",
            "rule_change": "a regulation or platform rule change",
            "charges_or_tax": "fees, charges or tax",
            "habit_discipline": "building or keeping a savings habit",
            "app_bug": "a bug or failure in the app",
            "fund_issue": "a problem with the fund itself",
            "cash_flow_or_life": "job loss, income cut, emergency or family costs",
        },
    },
    "failure_mode": {
        "unknown": "none",
        "help": "the main SIP problem the writer reports",
        "labels": {
            "instalment_failed": "an instalment, mandate or autopay failed or was not processed",
            "debited_after_cancel_or_twice": "money debited twice or after cancelling",
            "confusing_returns_or_progress": "cannot understand returns, P&L, NAV or progress",
            "losses_shake_confidence": "losses or red numbers shake their confidence",
            "cannot_pause_or_change_amount": "cannot pause, skip, modify or step up a SIP easily",
            "amount_too_high": "the amount is too high for their budget",
            "app_bug": "an app bug or crash not specific to instalments",
            "withdrawal_problem": "redemption or withdrawal delayed or blocked",
            "support_not_resolving": "customer support did not resolve the issue",
        },
    },
    "theme": {
        "unknown": "other",
        "help": "the main topic of the post",
        "labels": {
            "goals_and_motivation": "why they invest, goals, discipline",
            "platform_and_plan_choice": "choosing an app, AMC, direct or regular plan",
            "payments_and_mandates": "instalments, mandates, autopay, debits",
            "returns_and_progress": "returns, NAV, units, portfolio value",
            "sip_controls": "pausing, modifying, step-up, cancelling",
            "support_and_service": "customer support and service",
            "app_experience": "app design, features, speed, bugs",
            "charges_and_tax": "fees, charges, tax, ELSS",
            "learning": "learning how SIPs or mutual funds work",
        },
    },
    "expectation": {
        "unknown": "not_stated",
        "help": "what the writer expects a SIP to do for them",
        "labels": {
            "long_term_growth": "long-term growth or wealth creation", "habit": "a saving habit or discipline",
            "tax_benefit": "tax saving", "quick_gains": "quick or short-term gains", "steady_returns": "steady, safe returns",
        },
    },
    "checking": {
        "unknown": "not_stated",
        "help": "how often the writer says they check their SIP or portfolio",
        "labels": {"daily": "daily or more", "weekly": "weekly", "monthly": "monthly or on debit day", "rarely": "rarely"},
    },
    "confusion": {
        "unknown": "none",
        "help": "what confuses or worries them inside the app",
        "labels": {
            "returns_or_pnl": "returns, P&L or XIRR shown", "payment_status": "whether an instalment went through",
            "nav_or_units": "NAV dates or units allotted", "sip_dates": "SIP dates or schedules",
            "fund_details": "fund information", "charges": "charges or deductions",
        },
    },
    "help_seeking": {
        "unknown": "none",
        "help": "where they go outside the app when unsure",
        "labels": {
            "forum_or_community": "forums, Reddit or communities", "contacts_support": "contacting support",
            "other_apps_or_amc": "another app or the AMC's site", "youtube": "YouTube", "friends_or_family": "friends or family",
            "advisor": "a financial advisor",
        },
    },
    "experience": {
        "unknown": "not_stated",
        "help": "investing experience the writer states",
        "labels": {"first_time": "a first-time or new investor", "experienced": "has invested for years"},
    },
    "income": {
        "unknown": "not_stated",
        "help": "how the writer earns",
        "labels": {"salaried": "salaried", "student": "student", "self_employed": "self-employed or business",
                   "retired": "retired"},
    },
    "age": {
        "unknown": "not_stated",
        "help": "age the writer states",
        "labels": {"under_25": "under 25", "25_to_44": "25 to 44", "45_plus": "45 or older"},
    },
    "money_source": {
        "unknown": "not_stated",
        "help": "where the invested money comes from",
        "labels": {"salary": "salary", "business": "business income", "savings_or_bonus": "savings, bonus or gifts"},
    },
    "influence": {
        "unknown": "not_stated",
        "help": "who influenced their decision",
        "labels": {"own_research": "their own research", "youtube_or_finfluencer": "YouTube or finfluencers",
                   "friends_or_family": "friends or family", "advisor": "an advisor"},
    },
    "residency": {
        "unknown": "not_stated",
        "help": "residency the writer states",
        "labels": {"resident": "resident Indian", "nri": "non-resident Indian (NRI)"},
    },
}

SEGMENT_FIELDS = ("experience", "income", "age", "money_source", "influence", "residency")


def empty_tags() -> dict:
    return {name: spec["unknown"] for name, spec in FIELDS.items()}


UNKNOWN_WORDS = {"not_stated", "none", "other", "unknown", "n/a", "na", "null", "not_applicable", "not_mentioned"}


def _norm(value) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def clean(raw: dict) -> tuple[dict, int]:
    """Validated tags for one post, and how many labels were invalid (dropped).

    The model sometimes writes a list or a variant spelling ("Not stated", "first-time");
    a list keeps its first valid label, spellings are normalised, "unknown" words are silent.
    """
    tags, invalid = empty_tags(), 0
    for name, spec in FIELDS.items():
        value = raw.get(name)
        candidates = value if isinstance(value, list) else [value]
        candidates = [_norm(v) for v in candidates if v not in (None, "")]
        valid = [v for v in candidates if v in spec["labels"]]
        if valid:
            tags[name] = valid[0]
        elif any(v not in UNKNOWN_WORDS and v != spec["unknown"] for v in candidates):
            invalid += 1
    return tags, invalid


def prompt_reference() -> str:
    lines = []
    for name, spec in FIELDS.items():
        labels = "; ".join(f"{k} = {v}" for k, v in spec["labels"].items())
        lines.append(f"- {name} ({spec['help']}): {labels}")
    return "\n".join(lines)
