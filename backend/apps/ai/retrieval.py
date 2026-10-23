"""Simple keyword retrieval for knowledge entries and few-shot examples (no embeddings yet)."""

import re

from .models import FewShotExample, KnowledgeEntry

STOPWORDS = set(
    """a an the and or but if then so to of in on at for with from by is are was were be been am i you we
    they he she it my your our their me us them this that these those do does did have has had can could
    would should will shall may might please hi hello hey thanks thank ok okay yes no not what when where
    which who whom why how there here just also any some""".split()
)

# Lightweight intent hints -> knowledge categories.
CATEGORY_HINTS = {
    KnowledgeEntry.Category.PRICES: {"price", "prices", "cost", "costs", "much", "fee", "fees", "rate", "rates", "charge", "pricing", "expensive", "cheap"},
    KnowledgeEntry.Category.HOURS: {"open", "opening", "close", "closing", "hours", "today", "tomorrow", "weekend", "sunday", "saturday", "holiday", "time"},
    KnowledgeEntry.Category.BOOKING: {"book", "booking", "appointment", "slot", "slots", "available", "availability", "reserve", "reservation", "schedule"},
    KnowledgeEntry.Category.SHIPPING: {"ship", "shipping", "delivery", "deliver", "courier", "track", "tracking", "arrive"},
    KnowledgeEntry.Category.REFUNDS: {"refund", "return", "returns", "exchange", "money", "back", "cancel", "cancellation"},
    KnowledgeEntry.Category.SERVICE_AREAS: {"area", "areas", "location", "locations", "near", "city", "where", "address", "come"},
    KnowledgeEntry.Category.CONTACT: {"phone", "email", "call", "contact", "address", "reach"},
    KnowledgeEntry.Category.PRODUCTS: {"product", "products", "service", "services", "offer", "sell", "menu", "stock"},
}

ALWAYS_INCLUDE = (KnowledgeEntry.Category.DESCRIPTION,)
INSTRUCTION_CATEGORIES = (KnowledgeEntry.Category.CUSTOM,)


def tokenize(text):
    return [t for t in re.findall(r"[\w']+", (text or "").lower()) if t not in STOPWORDS and len(t) > 1]


def retrieve_knowledge(workspace, query_text, limit=6):
    tokens = set(tokenize(query_text))
    hinted = {cat for cat, words in CATEGORY_HINTS.items() if tokens & words}
    scored = []
    always = []
    for entry in KnowledgeEntry.objects.filter(workspace=workspace, active=True):
        if entry.category in INSTRUCTION_CATEGORIES:
            continue  # rendered as business instructions, not as facts
        if entry.category in ALWAYS_INCLUDE:
            always.append(entry)
            continue
        kw = set(tokenize(entry.keywords))
        title = set(tokenize(entry.title))
        content = set(tokenize(entry.content))
        score = 3 * len(tokens & kw) + 2 * len(tokens & title) + len(tokens & content)
        if entry.category in hinted:
            score += 3
        if score > 0:
            scored.append((score, entry.updated_at, entry))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return always[:2] + [e for _, _, e in scored[:limit]]


def business_instructions(workspace):
    return list(
        KnowledgeEntry.objects.filter(
            workspace=workspace, active=True, category__in=INSTRUCTION_CATEGORIES
        ).order_by("title")[:10]
    )


def retrieve_examples(workspace, query_text, limit=3):
    tokens = set(tokenize(query_text))
    examples = list(FewShotExample.objects.filter(workspace=workspace, active=True, authorized=True)[:200])
    scored = []
    for ex in examples:
        overlap = len(tokens & set(tokenize(ex.customer_message + " " + ex.situation)))
        scored.append((overlap, ex.created_at, ex))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    picked = [ex for score, _, ex in scored if score > 0][:limit]
    if not picked:
        picked = examples[:2]  # most recent, to convey general style
    return picked
