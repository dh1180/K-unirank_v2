from django import template

from admissions.services.metrics import metric_label, metric_unit


register = template.Library()


@register.filter
def admission_metric_label(value):
    return metric_label(value)


@register.filter
def admission_metric_unit(value):
    return metric_unit(value)
