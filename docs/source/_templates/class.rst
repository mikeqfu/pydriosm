{{ objname | escape | underline }}

.. currentmodule:: {{ module }}.{{ objname }}

.. autoclass:: {{ module }}.{{ objname }}
    {% block attributes %}
    {% if attributes %}
    .. rubric:: {{ _('Attributes') }}
    .. autosummary::
        :template: base.rst
        :toctree:
        {% for item in attributes %}
        {%- if (not item.startswith('_')) and (item not in inherited_members) %}
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
        {% for item in methods %}
        {%- if (not item.startswith('_') or item in ['__call__']) and (item not in inherited_members) %}
        {{ item }}
        {%- endif -%}
        {%- endfor %}
    {% endif %}
    {% endblock %}

