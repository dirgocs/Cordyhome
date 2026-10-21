"""Templates de valor (`value_template`) da descoberta do Home Assistant.

Os aparelhos mandam trechos Jinja como `{{ value_json.power }}` para dizer onde está o valor
dentro da mensagem. Rodam num ambiente isolado (sandbox): o template vem do aparelho e não
pode acessar nada do hub.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from jinja2 import StrictUndefined, TemplateError, Undefined
from jinja2.exceptions import SecurityError
from jinja2.sandbox import ImmutableSandboxedEnvironment


def _is_defined(value: Any) -> Any:
    if isinstance(value, Undefined):
        raise TemplateError("valor ausente")
    return value


# Limites contra templates que travariam o hub (laços enormes, textos gigantes).
MAX_REPEAT = 10_000
MAX_EXPONENT = 64
LOOP = re.compile(r"{%-?\s*(for|macro|call)\b")


class _Environment(ImmutableSandboxedEnvironment):
    intercepted_binops = frozenset({"*", "**"})

    def call_binop(self, context, operator, left, right):
        if operator == "**" and isinstance(right, int | float) and abs(right) > MAX_EXPONENT:
            raise SecurityError("expoente grande demais")
        if operator == "*":
            for seq, times in ((left, right), (right, left)):
                sized = isinstance(seq, str | list | tuple) and isinstance(times, int)
                if sized and len(seq) * times > MAX_REPEAT:
                    raise SecurityError("texto grande demais")
        return super().call_binop(context, operator, left, right)


_env = _Environment(undefined=StrictUndefined, autoescape=False)
_env.filters["is_defined"] = _is_defined


@lru_cache(maxsize=256)
def _compile(source: str):
    if LOOP.search(source):
        raise SecurityError("laços não são aceitos")
    return _env.from_string(source)


def parse_json(payload: str) -> Any:
    try:
        return json.loads(payload)
    except ValueError:
        return None


def render(source: str | None, payload: str, **extra: Any) -> str | None:
    """Aplica o template à mensagem. Sem template, devolve a própria mensagem.

    Devolve None quando o template não se aplica a esta mensagem (campo ausente, erro).
    """
    if not source:
        return payload
    try:
        result = _compile(source).render(value=payload, value_json=parse_json(payload), **extra)
    except (TemplateError, TypeError, ValueError, AttributeError, KeyError):
        return None
    return result.strip()
