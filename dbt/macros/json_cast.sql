{# vaastav CSV cells arrive as strings. Empty strings become null before casting. #}
{% macro json_num(col, key, type='numeric') -%}
    cast(nullif({{ col }} ->> '{{ key }}', '') as {{ type }})
{%- endmacro %}

{% macro json_bool(col, key) -%}
    case lower(nullif({{ col }} ->> '{{ key }}', ''))
        when 'true' then true when '1' then true
        when 'false' then false when '0' then false
    end
{%- endmacro %}
