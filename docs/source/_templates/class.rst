{{ objname | escape | underline }}

.. currentmodule:: {{ module }}.{{ objname }}

.. autoclass:: {{ module }}.{{ objname }}
    {% block attributes %}
    {% if attributes %}
    .. rubric:: {{ _('Attributes') }}
    .. autosummary::
        :template: base.rst
        :toctree:
        {% for item in all_attributes %}
        {%- if not item.startswith('_') %}
        {{ item }}
        {%- endif -%}
        {%- endfor %}
    {% endif %}
    {% endblock %}
    {% block methods %}
    {% if methods %}
    .. rubric:: {{ _('Methods') }}
    .. autosummary::
        :template: base.rst
        :toctree:
        {% for item in all_methods %}
        {%- if not item.startswith('_') or item in ['__call__'] %}
        {{ item }}
        {%- endif -%}
        {%- endfor %}
    {% endif %}
    {% endblock %}

