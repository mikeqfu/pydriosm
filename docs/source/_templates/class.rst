{{ objname | escape | underline }}

.. currentmodule:: {{ module }}.{{ objname }}

.. autoclass:: {{ module }}.{{ objname }}

    {% block attributes %}
    {% set ns = namespace(attrs=[]) %}
    {% for item in all_attributes %}
        {% if not item.startswith('_') %}
            {% set _ = ns.attrs.append(item) %}
        {% endif %}
    {% endfor %}
    {% if ns.attrs %}
    .. rubric:: {{ _('Attributes') }}
    .. autosummary::
        :template: base.rst
        :toctree:
        {% for item in ns.attrs %}
        {{ item }}
        {% endfor %}
    {% endif %}
    {% endblock %}

    {% block methods %}
    {% set ns = namespace(methods=[]) %}
    {% for item in all_methods %}
        {% if not item.startswith('_') or item in ['__call__'] %}
            {% set _ = ns.methods.append(item) %}
        {% endif %}
    {% endfor %}
    {% if ns.methods %}
    .. rubric:: {{ _('Methods') }}
    .. autosummary::
        :template: base.rst
        :toctree:
        {% for item in ns.methods %}
        {{ item }}
        {% endfor %}
    {% endif %}
    {% endblock %}

