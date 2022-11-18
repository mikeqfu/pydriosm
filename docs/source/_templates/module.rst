{{ module | escape | underline }}

.. currentmodule:: {{ fullname }}

.. automodule:: {{ fullname }}

{% if functions %}
.. rubric:: Functions
.. autosummary::
    :template: function.rst
    :toctree: .
    {% for function in functions %}
    {{ function }}
    {% endfor %}
{% endif %}
{% if classes %}
.. rubric:: Classes
.. autosummary::
    :template: class.rst
    :toctree: .
    {% for class in classes %}
    {{ class }}
    {% endfor %}
{% endif %}

