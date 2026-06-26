from django import template
import os

register = template.Library()

@register.filter
def basename(value):
    try:
        return os.path.basename(value.name)
    except:
        return str(value)