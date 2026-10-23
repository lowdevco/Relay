"""Create a local demo workspace with sample knowledge + style examples.

    python manage.py seed_demo

Local development only. Demo login: username `demo`, password `demo-pass-2026`.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.models import FewShotExample, KnowledgeEntry, PersonaProfile
from apps.core.models import Membership, Workspace
from apps.core.services import ensure_workspace_defaults
from apps.whatsapp.models import WhatsAppIntegration

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-pass-2026"

KNOWLEDGE = [
    ("description", "About us", "Bloom Hair Studio is a small hair salon in Leeds city centre offering cuts, colour and styling."),
    ("hours", "Opening hours", "Tuesday to Saturday 10:00-18:00. Closed Sunday and Monday.", "open hours closed today tomorrow"),
    ("prices", "Haircut prices", "Women's cut and blow-dry £45. Men's cut £25. Kids (under 12) £18.", "price cost haircut cut"),
    ("prices", "Colour prices", "Full colour from £70. Balayage from £120. Prices depend on hair length; final quote after consultation.", "colour color balayage highlights"),
    ("booking", "How to book", "We can't confirm bookings over chat. Share your preferred day and time and a team member will confirm availability.", "book appointment slot available"),
    ("policy", "Cancellation policy", "Please give at least 24 hours notice to cancel or reschedule.", "cancel reschedule"),
    ("contact", "Address", "12 Park Row, Leeds LS1 5HD.", "address where location"),
    ("custom", "Escalate complaints", "If a customer is unhappy with a service, apologise and say the salon manager will reply personally."),
]

EXAMPLES = [
    ("Hi, do you have any slots available tomorrow?", "Hey! Let me check tomorrow's slots for you 😊 What time of day works best?", "booking"),
    ("How much is a men's haircut?", "Hi! A men's cut is £25. Want me to find you a time?", "pricing"),
    ("Are you open on Monday?", "Hey! We're closed on Mondays, but we're open Tuesday to Saturday 10–6. Does another day suit you?", "hours"),
]


class Command(BaseCommand):
    help = "Create a demo workspace for local development."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True.")
        User = get_user_model()
        user, created = User.objects.get_or_create(username=DEMO_USERNAME)
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        membership = Membership.objects.filter(user=user).select_related("workspace").first()
        if membership:
            ws = membership.workspace
        else:
            ws = Workspace.objects.create(name="Bloom Hair Studio", timezone="Europe/London")
            Membership.objects.create(user=user, workspace=ws, role="owner")
        ensure_workspace_defaults(ws)
        PersonaProfile.objects.filter(workspace=ws).update(
            business_name="Bloom Hair Studio",
            assistant_role="friendly booking assistant for a hair salon",
            formality=2,
            friendliness=5,
            greetings="Hey!, Hi!",
            closings="See you soon!",
            phrases_to_avoid="Dear valued customer; As an AI language model",
        )
        if not KnowledgeEntry.objects.filter(workspace=ws).exists():
            for row in KNOWLEDGE:
                cat, title, content, *kw = row
                KnowledgeEntry.objects.create(workspace=ws, category=cat, title=title, content=content, keywords=kw[0] if kw else "")
        if not FewShotExample.objects.filter(workspace=ws).exists():
            for q, a, situation in EXAMPLES:
                FewShotExample.objects.create(workspace=ws, customer_message=q, preferred_reply=a, situation=situation)
        pid = settings.WHATSAPP_PHONE_NUMBER_ID or "100000000000001"
        if not WhatsAppIntegration.objects.filter(workspace=ws).exists() and not WhatsAppIntegration.objects.filter(phone_number_id=pid).exists():
            WhatsAppIntegration.objects.create(
                workspace=ws, phone_number_id=pid, business_account_id=settings.WHATSAPP_BUSINESS_ACCOUNT_ID, status="pending"
            )
        self.stdout.write(self.style.SUCCESS(f"Demo workspace ready: '{ws.name}'. Login: {DEMO_USERNAME} / {DEMO_PASSWORD}"))
