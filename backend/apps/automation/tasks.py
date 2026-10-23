from apps.core.jobs import register

from . import pipeline


@register("automation.process_inbound")
def process_inbound(message_id):
    return pipeline.process_inbound(message_id)


@register("automation.summarize")
def summarize(conversation_id):
    return pipeline.summarize(conversation_id)
