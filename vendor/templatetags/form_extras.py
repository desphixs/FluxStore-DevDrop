# customer/templatetags/form_extras.py
from django import template
from django.utils.safestring import mark_safe
from django.forms.boundfield import BoundField
import re

register = template.Library()

@register.filter(name="add_class")
def add_class(field, css):
    """
    Safely add CSS classes to a form field (BoundField) or to a pre-rendered HTML string.
    - If `field` is a BoundField: render with merged classes.
    - If `field` is a string: inject/append class=... into the first tag.
    - Otherwise: return as-is.
    """
    try:
        # BoundField path (best case)
        if isinstance(field, BoundField) or hasattr(field, "as_widget"):
            # Merge with widget's existing classes if any
            existing = ""
            try:
                existing = field.field.widget.attrs.get("class", "")  # type: ignore[attr-defined]
            except Exception:
                existing = ""
            classes = (existing + " " + (css or "")).strip()
            return field.as_widget(attrs={"class": classes})

        # Already-rendered HTML string — inject class
        s = str(field)
        if "<" in s and ">" in s:
            # If there's already a class attr, append
            if 'class="' in s:
                s = re.sub(r'class="([^"]*)"', lambda m: f'class="{(m.group(1) + " " + (css or "")).strip()}"', s, 1)
            else:
                # Add class attr to the first opening tag
                s = re.sub(r'(<\w+)(\s*)', r'\1 class="' + (css or "") + r'"\2', s, 1)
            return mark_safe(s)
    except Exception:
        # Fall through to returning the original field if anything goes wrong
        pass
    return field
