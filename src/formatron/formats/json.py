"""
The module defines the `JsonExtractor` class, which is used to extract data from a string in JSON format.
"""
import collections
import decimal
import json
import types
import typing

from frozendict import frozendict

from formatron import extractor, schemas
from formatron.formats.utils import escape_identifier


__all__ = ["JsonExtractor", "strict_schema"]


"""
Whether to raise an error if the grammar cannot be precisely constructed from the schema.
True by default. 

If set to False, heuristics will be used to construct the grammar that may not fully describe the schema's constraints.
"""
strict_schema = True

SPACE_NONTERMINAL = "[ \t\n]*"

GRAMMAR_HEADER = rf"""integer ::= #"{SPACE_NONTERMINAL}-?(0|[1-9][0-9]*)";
number ::= #"{SPACE_NONTERMINAL}-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'{SPACE_NONTERMINAL}"([^\\\\"\u0000-\u001f]|\\\\["\\\\bfnrt]|\\\\u[0-9A-Fa-f]{{4}})*"';
boolean ::= #"{SPACE_NONTERMINAL}(true|false)";
null ::= #"{SPACE_NONTERMINAL}null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"{SPACE_NONTERMINAL},";
colon ::= #"{SPACE_NONTERMINAL}:";
object_begin ::= #"{SPACE_NONTERMINAL}\\{{";
object_end ::= #"{SPACE_NONTERMINAL}\\}}";
array_begin ::= #"{SPACE_NONTERMINAL}\\[";
array_end ::= #"{SPACE_NONTERMINAL}\\]";
"""

_REGEX_METACHARACTERS = frozenset("\\.^$|?*+()[]{}")


def regex_escape(text: str) -> str:
    """
    Escape every regex metacharacter in `text` so it matches literally.
    """
    return "".join(f"\\{c}" if c in _REGEX_METACHARACTERS else c for c in text)


def kbnf_string_escape(text: str) -> str:
    """
    Escape `text` for the inside of a single-quoted KBNF string literal (`'...'` or `#'...'`).

    Backslashes and single quotes are escaped and control characters are written as
    KBNF escapes, so no input can terminate the literal early. Regex metacharacters are
    *not* escaped here; use `regex_escape` first when the text must match literally.
    """
    result = []
    for c in text:
        code = ord(c)
        if c == "\\":
            result.append("\\\\")
        elif c == "'":
            result.append("\\'")
        elif c == "\n":
            result.append("\\n")
        elif c == "\t":
            result.append("\\t")
        elif c == "\r":
            result.append("\\r")
        elif code < 0x20 or code == 0x7F:
            result.append(f"\\u{code:04x}")
        else:
            result.append(c)
    return "".join(result)


def kbnf_regex_term(pattern: str, *, leading_space: bool = True) -> str:
    """
    Wrap a raw regex pattern as a KBNF regex terminal, optionally allowing leading JSON whitespace.
    """
    prefix = SPACE_NONTERMINAL if leading_space else ""
    return f"#'{prefix}{kbnf_string_escape(pattern)}'"


def json_literal_term(value: typing.Any) -> str:
    """
    A KBNF terminal matching exactly the JSON encoding of `value` (a string, number, bool, or None),
    with leading JSON whitespace allowed.
    """
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return kbnf_regex_term(regex_escape(text))


def from_str_to_kbnf_str(s: str) -> str:
    """
    Convert a string to a kbnf terminal matching its JSON string encoding.

    Args:
        s: The string to convert.

    Returns:
        The kbnf string.
    """
    return json_literal_term(s)


def _object_rules(nonterminal: str, pairs: list[tuple[str, bool]]) -> str:
    """
    Emit the rules for an object whose members appear in schema order and whose optional
    members may be omitted entirely (key and value).

    A chain of `tail` nonterminals is used so that every production contains at most one
    optional group: the grammar stays linear in the number of members instead of the
    exponential blow-up that a production with many nullable symbols causes during
    simplification.

    Args:
        nonterminal: The object's nonterminal.
        pairs: `(pair_text, required)` per member, in order; `pair_text` is `key colon value`.
    """
    n = len(pairs)
    if n == 0:
        return f"{nonterminal} ::= object_begin object_end;\n"
    required_after = [False] * (n + 1)
    for i in range(n - 1, -1, -1):
        required_after[i] = pairs[i][1] or required_after[i + 1]

    def tail(i: int) -> str:
        return escape_identifier(f"{nonterminal}_tail{i}")

    lines = [f"{nonterminal} ::= object_begin {tail(0)}{'' if required_after[0] else '?'} object_end;\n"]
    for i, (pair, required) in enumerate(pairs):
        alternatives = []
        if i == n - 1:
            alternatives.append(pair)
        elif required_after[i + 1]:
            alternatives.append(f"{pair} comma {tail(i + 1)}")
        else:
            alternatives.append(f"{pair} (comma {tail(i + 1)})?")
        if not required and i < n - 1:
            alternatives.append(tail(i + 1))
        lines.append(f"{tail(i)} ::= {' | '.join(alternatives)};\n")
    return "".join(lines)

_type_to_nonterminals = []



def register_generate_nonterminal_def(
        generate_nonterminal_def: typing.Callable[
            [typing.Type, str],
            typing.Optional[typing.Tuple[str,
                                         typing.List[typing.Tuple[typing.Type, str]]]]]) -> None:
    """
    Register a callable to generate nonterminal definition from a type.
    The callable returns (nonterminal_definition, [(sub_type, sub_nonterminal), ...])
    if the type is supported by this callable, otherwise None.
    [(sub_type, sub_nonterminal), ...] are the types and nonterminals used in nonterminal_definition that may need
    to be generated in the grammar too.

    Args:
        generate_nonterminal_def: A callable to generate nonterminal definition from a type.
    """
    _type_to_nonterminals.append(generate_nonterminal_def)


def _register_all_predefined_types():
    def schema(current: typing.Type, nonterminal: str):
        if isinstance(current, type) and not isinstance(current, types.GenericAlias) \
                and issubclass(current, schemas.schema.Schema):
            result = []
            pairs = []
            for field, _field_info in current.fields().items():
                field_name = escape_identifier(f"{nonterminal}_{field}")
                key = from_str_to_kbnf_str(field)
                pairs.append((f"{key} colon {field_name}", _field_info.required))
                result.append((_field_info, field_name))
            return _object_rules(nonterminal, pairs), result
        return None

    def field_info(current: typing.Type, nonterminal: str):
        if isinstance(current, schemas.schema.FieldInfo):
            # Optional members are omitted as a whole (key and value) by `_object_rules`;
            # emitting an optional *value* produced invalid JSON such as `"b": ,`.
            return "", [(current.annotation, nonterminal)]
        return None

    def string_metadata(current: typing.Type, nonterminal: str):
        min_length = current.metadata.get("min_length")
        max_length = current.metadata.get("max_length")
        pattern = current.metadata.get("pattern")
        substring_of = current.metadata.get("substring_of")
        if pattern:
            # Check if pattern contains unescaped anchors (^ or $)
            # First replace escaped anchors with placeholders
            temp_pattern = pattern.replace(r'\^', '').replace(r'\$', '').replace(r'\\A', '').replace(r'\\z', '')
            # Check for unescaped anchors
            if '^' in temp_pattern or '$' in temp_pattern or '\A' in temp_pattern or '\z' in temp_pattern:
                if strict_schema:
                    raise ValueError(f"Pattern '{pattern}' contains unescaped anchors (^, $, \\A, \\z) which are not allowed")
                else:
                    print(f"Warning: pattern '{pattern}' contains unescaped anchors (^, $, \\A, \\z) which are not allowed in schema {current} from {nonterminal}")
                    pattern = pattern.strip('^$')
            if strict_schema:
                assert not (min_length or max_length or substring_of), "pattern is mutually exclusive with min_length, max_length and substring_of"
            else:
                if min_length or max_length or substring_of:
                    print(f"Warning: pattern is mutually exclusive with min_length, max_length and substring_of in schema {current} from {nonterminal}")
                    min_length = None
                    max_length = None
                    substring_of = None
        if substring_of:
            if strict_schema:
                assert not (min_length or max_length or pattern), "substring_of is mutually exclusive with min_length, max_length and pattern"
            else:
                if min_length or max_length or pattern:
                    print(f"Warning: substring_of is mutually exclusive with min_length, max_length and pattern in schema {current} from {nonterminal}")
                    min_length = None
                    max_length = None
                    pattern = None
        repetition_map = {
            (True, False): f"{{{min_length},}}",
            (False, True): f"{{0,{max_length}}}",
            (True, True): f"{{{min_length},{max_length}}}"
        }
        repetition = repetition_map.get((min_length is not None, max_length is not None))
        if repetition is not None:
            return fr"""{nonterminal} ::= #'{SPACE_NONTERMINAL}"([^\\\\"\u0000-\u001f]|\\\\["\\\\bfnrt/]|\\\\u[0-9A-Fa-f]{{4}}){repetition}"';
""", []
        if pattern is not None:
            quoted_pattern = '"(?:' + pattern + ')"'  # group so a top-level `|` stays inside the quotes
            return f"{nonterminal} ::= {kbnf_regex_term(quoted_pattern)};\n", []
        if substring_of is not None:
            return f"""{nonterminal} ::= #'{SPACE_NONTERMINAL}' '"' #substrs{repr(substring_of)} '"';\n""", []
    
    def number_metadata(current: typing.Type, nonterminal: str):
        gt = current.metadata.get("gt")
        ge = current.metadata.get("ge")
        lt = current.metadata.get("lt")
        le = current.metadata.get("le")
        
        prefix_map = {
            (gt, 0): "",
            (ge, 0): "0|",
            (lt, 0): "-",
            (le, 0): "0|-",
        }
        
        for (condition, value), prefix in prefix_map.items():
            if condition is not None and condition == value:
                if issubclass(current.type, int):
                    return f"""{nonterminal} ::= #'{SPACE_NONTERMINAL}{prefix}[1-9][0-9]*';\n""", []
                elif issubclass(current.type, float):
                    return f"""{nonterminal} ::= #'{SPACE_NONTERMINAL}{prefix}[1-9][0-9]*(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?';\n""", []
        if strict_schema:
            raise ValueError(f"{current.type.__name__} metadata {current.metadata} is not supported in json_generators!")
        else:
            print(f"Warning: {current.type.__name__} metadata {current.metadata} is not supported in json_generators!")
            return "", [(current.type, nonterminal)]
    
    def sequence_metadata(current: typing.Type, nonterminal: str):
        min_items = current.metadata.get("min_length")
        max_items = current.metadata.get("max_length")
        prefix_items = current.metadata.get("prefix_items")
        additional_items = current.metadata.get("additional_items", True)
        if min_items is None and max_items is None and prefix_items is None:
            return None
        min_items = int(min_items or 0)
        prefix = tuple(prefix_items or ())
        prefix_len = len(prefix)
        if not additional_items:
            if min_items > prefix_len:
                raise ValueError(f"min_items {min_items} is greater than the number of prefix_items {prefix_len} and additional_items is not allowed")
            max_items = prefix_len if max_items is None else min(max_items, prefix_len)
        if max_items is not None and max_items < min_items:
            raise ValueError(f"max_items {max_items} is smaller than min_items {min_items}")
        args = typing.get_args(current.type)
        item_type = args[0] if args else typing.Any
        item_nonterminal = f"{nonterminal}_item"
        prefix_nonterminals = [f"{item_nonterminal}_{i}" for i in range(prefix_len)]
        rules = []
        alternatives = []

        def optional_chain(count: int) -> str:
            """A nonterminal accepting between 0 and `count` further `comma item` pairs, as a
            chain of rules so grammar size stays linear and no production nests optionals."""
            names = [f"{item_nonterminal}_more{k}" for k in range(1, count + 1)]
            for k, name in enumerate(names, start=1):
                continuation = f" {names[k - 2]}" if k > 1 else ""
                rules.append(f"{name} ::= (comma {item_nonterminal}{continuation})?;")
            return names[-1]

        # Lengths that end inside the prefix (including the empty array when allowed).
        upper = prefix_len if max_items is None else min(prefix_len, max_items)
        for length in range(min_items, upper + 1):
            alternatives.append(" comma ".join(prefix_nonterminals[:length]))
        uses_item = max_items is None or max_items > prefix_len
        if uses_item:
            head = prefix_nonterminals + [item_nonterminal] * max(min_items - prefix_len, 0)
            if max_items is None:
                if head:
                    alternatives.append(f"{' comma '.join(head)} (comma {item_nonterminal})*")
                else:
                    alternatives.append(f"{item_nonterminal} (comma {item_nonterminal})*")
            else:
                if not head:
                    head = [item_nonterminal]
                optional = max_items - len(head)
                tail = f" {optional_chain(optional)}" if optional > 0 else ""
                alternatives.append(f"{' comma '.join(head)}{tail}")
        rules.insert(0, f"{nonterminal} ::= " + " | ".join(f"array_begin {alt} array_end" for alt in alternatives) + ";")
        pending = list(zip(prefix, prefix_nonterminals))
        if uses_item:
            pending.append((item_type, item_nonterminal))
        return "\n".join(rules) + "\n", pending

    def is_sequence_like(current: typing.Type) -> bool:
        """
        Check if the given type is sequence-like.

        This function returns True for:
        - typing.Sequence
        - typing.List
        - typing.Tuple
        - Any subclass of collections.abc.Sequence
        - list
        - tuple

        Args:
            current: The type to check.

        Returns:
            bool: True if the type is sequence-like, False otherwise.
        """
        original = typing.get_origin(current)
        if original is None:
            original = current
        return (
            original is typing.Sequence or
            original is typing.List or
            original is typing.Tuple or
            (isinstance(original, type) and (issubclass(original, collections.abc.Sequence) or
            issubclass(original, list) or
            issubclass(original, tuple)))
        )

    def metadata(current: typing.Type, nonterminal: str):
        if isinstance(current, schemas.schema.TypeWithMetadata):
            original = typing.get_origin(current.type)
            if original is None:
                original = current.type
            if not current.metadata:
                return "", [(current.type, nonterminal)]
            if isinstance(current.type, type) and issubclass(current.type, str):
                return string_metadata(current, nonterminal)
            elif isinstance(current.type, type) and issubclass(current.type, (int, float)):
                return number_metadata(current, nonterminal)
            elif is_sequence_like(original):
                return sequence_metadata(current, nonterminal)
        return None

    def builtin_sequence(current: typing.Type, nonterminal: str):
        original = typing.get_origin(current)
        if original is None:
            original = current
        if is_sequence_like(original):
            new_nonterminal = f"{nonterminal}_value"
            annotation = typing.get_args(current)
            if not annotation:
                annotation = typing.Any
            else:
                annotation = annotation[0]
            return f"{nonterminal} ::= array_begin ({new_nonterminal} (comma {new_nonterminal})*)? array_end;\n", \
                [(annotation, new_nonterminal)]
        return None

    def builtin_dict(current: typing.Type, nonterminal: str):
        original = typing.get_origin(current)
        if original is None:
            original = current
        if original is typing.Mapping or isinstance(original, type) and issubclass(original,
                                                                                   collections.abc.Mapping):
            new_nonterminal = f"{nonterminal}_value"
            args = typing.get_args(current)
            if not args:
                value = typing.Any
            else:
                assert issubclass(
                    args[0], str), f"{args[0]} is not string!"
                value = args[1]
            if value is typing.Any:
                return f"{nonterminal} ::= object;\n", []
            return f"{nonterminal} ::=" \
                f" object_begin (string colon {new_nonterminal} (comma string colon {new_nonterminal})*)?" \
                f" object_end;\n", \
                [(value, new_nonterminal)]
        return None

    def builtin_tuple(current: typing.Type, nonterminal: str):
        if typing.get_origin(current) is tuple or isinstance(current, type) and issubclass(current, tuple):
            args = typing.get_args(current)
            new_nonterminals = []
            result = []
            for i, arg in enumerate(args):
                result.append(arg)
                new_nonterminals.append(f"{nonterminal}_{i}")
            return f"{nonterminal} ::=array_begin {' comma '.join(new_nonterminals)} array_end;\n", \
                zip(result, new_nonterminals)

    def builtin_union(current: typing.Type, nonterminal: str):
        if typing.get_origin(current) is typing.Union:
            args = typing.get_args(current)
            assert args, f"{current} from {nonterminal} cannot be an empty union!"
            new_nonterminals = []
            result = []
            for i, arg in enumerate(args):
                result.append(arg)
                new_nonterminals.append(f"{nonterminal}_{i}")
            return f"{nonterminal} ::= {' | '.join(new_nonterminals)};\n", zip(result, new_nonterminals)

    def builtin_literal(current: typing.Type, nonterminal: str):
        if typing.get_origin(current) is typing.Literal:
            args = typing.get_args(current)
            assert args, f"{current} from {nonterminal} cannot be an empty literal!"
            new_items = []
            result = []
            for i, arg in enumerate(args):
                if isinstance(arg, (str, bool, int, float)):
                    new_items.append(json_literal_term(arg))
                elif arg is None:
                    new_items.append("null")
                elif isinstance(arg, tuple):
                    for j,item in enumerate(arg):
                        new_nonterminal = f"{nonterminal}_{i}_{j}"
                        result.append((typing.Literal[item], new_nonterminal))
                    new_item = f"(array_begin {' comma '.join(map(lambda x:x[1], result))} array_end)"
                    new_items.append(new_item)
                elif isinstance(arg, frozendict):
                    for key, value in arg.items():
                        new_nonterminal = f"{nonterminal}_{i}_{key}"
                        result.append((typing.Literal[value], new_nonterminal))
                    new_item = f"object_begin {' comma '.join(map(lambda x:x[1], result))} object_end"
                    new_items.append(new_item)
                else:
                    new_nonterminal = f"{nonterminal}_{i}"
                    result.append((arg, new_nonterminal))
                    new_items.append(new_nonterminal)
            return f"{nonterminal} ::= {' | '.join(new_items)};\n", result

    def builtin_simple_types(current: typing.Type, nonterminal: str):
        if isinstance(current, type) and issubclass(current, bool):
            return f"{nonterminal} ::= boolean;\n", []
        elif isinstance(current, type) and issubclass(current, int):
            return f"{nonterminal} ::= integer;\n", []
        elif isinstance(current, type) and issubclass(current, float):
            return f"{nonterminal} ::= number;\n", []
        elif isinstance(current, type) and issubclass(current, decimal.Decimal):
            return f"{nonterminal} ::= number;\n", []
        elif isinstance(current, type) and issubclass(current, str):
            return f"{nonterminal} ::= string;\n", []
        elif isinstance(current, type) and issubclass(current, type(None)):
            return f"{nonterminal} ::= null;\n", []
        elif current is typing.Any:
            return f"{nonterminal} ::= json_value;\n", []
        elif isinstance(current, typing.NewType):
            current: typing.NewType
            return "", [(current.__supertype__, nonterminal)]

    register_generate_nonterminal_def(builtin_simple_types)
    register_generate_nonterminal_def(schema)
    register_generate_nonterminal_def(field_info)
    register_generate_nonterminal_def(metadata)
    register_generate_nonterminal_def(builtin_tuple)
    register_generate_nonterminal_def(builtin_literal)
    register_generate_nonterminal_def(builtin_union)
    register_generate_nonterminal_def(builtin_sequence)
    register_generate_nonterminal_def(builtin_dict)

def _generate_kbnf_grammar(schema: schemas.schema.Schema|collections.abc.Sequence, start_nonterminal: str) -> str:
    """
    Generate a KBNF grammar string from a schema for JSON format.

    Args:
        schema: The schema to generate a grammar for.
        start_nonterminal: The start nonterminal of the grammar. Default is "start".

    Returns:
        The generated KBNF grammar string.
    """
    type_id_to_nonterminal = {
        id(int): "integer",
        id(float): "number",
        id(str): "string",
        id(bool): "boolean",
        id(type(None)): "null",
        id(list): "array",
        id(dict): "object",
        id(typing.Any): "json_value",
    }
    result = [GRAMMAR_HEADER]
    nonterminals = set()
    stack = [(schema, start_nonterminal)]
    while stack:
        (current, nonterminal) = stack.pop()
        type_id = id(current)
        if type_id in type_id_to_nonterminal:
            line = f"{nonterminal} ::= {type_id_to_nonterminal[type_id]};\n"
            result.append(line)
            continue
        type_id_to_nonterminal[type_id] = nonterminal
        for i in _type_to_nonterminals:
            value = i(current, nonterminal)
            if value is not None:
                line, to_stack = value
                result.append(line)
                stack.extend(to_stack)
                nonterminals.add(nonterminal)
                break
        else:
            raise TypeError(
                f"{current} from {nonterminal} is not supported in json_generators!")
    return "".join(result)


class JsonExtractor(extractor.NonterminalExtractor):
    """
    An extractor that loads json data to an object from a string.
    """

    def __init__(self, nonterminal: str, capture_name: typing.Optional[str], schema: schemas.schema.Schema|collections.abc.Sequence,
                 to_object: typing.Callable[[str], schemas.schema.Schema]):
        """
        Create a json extractor from a given schema or a list of supported types.

        Currently, the following data types are supported:

        - bool
        - int
          - positive int
          - negative int
          - nonnegative int
          - nonpositive int
        - float
          - positive float
          - negative float
          - nonnegative float
          - nonpositive float
        - str
          - optionally with min_length, max_length and pattern constraints
            - length is measured in UTF-8 character number after json parsing
            - *Warning*: too large difference between min_length and max_length can lead to enormous memory consumption!
            - pattern is mutually exclusive with min_length and max_length
            - pattern will be compiled to a regular expression so all caveats of regular expressions apply
            - pattern currently is automatically anchored at both ends
            - the generated json could be invalid if the pattern allows invalid content between the json string's quotes.
              - for example, `pattern=".*"` will allow '\"' to appear in the json string which is forbidden by JSON standard.
          - also supports substring_of constraint which constrains the string to be a substring of a given string
            - the generated json could be invalid if the given string contains invalid content when put into the json string's quotes.
              - for example, `substring_of="abc\""` will allow '\"' to appear in the json string which is forbidden by JSON standard.
        - NoneType
        - typing.Any
        - Subclasses of collections.abc.Mapping[str,T] and typing.Mapping[str,T] where T is a supported type,
        - Subclasses of collections.abc.Sequence[T] and typing.Sequence[T] where T is a supported type.
          - optionally with `minItems`, `maxItems`, `prefixItems` constraints
          - *Warning*: too large difference between minItems and maxItems can lead to very slow performance!
          - *Warning*: By json schema definition, prefixItems by default allows additional items and missing items in the prefixItems, which may not be the desired behavior and can lead to very slow performance if prefixItems is long!
        - tuple[T1,T2,...] where T1,T2,... are supported types. The order, type and number of elements will be preserved.
        - typing.Literal[x1,x2,...] where x1, x2, ... are instances of int, string, bool or NoneType, or another typing.Literal[y1,y2,...]
        - typing.Union[T1,T2,...] where T1,T2,... are supported types.
        - schemas.Schema where all its fields' data types are supported. Recursive schema definitions are supported as well.
          - *Warning*: while not required field is supported, they can lead to very slow performance and/or enormous memory consumption if there are too many of them!
        
        Args:
            nonterminal: The nonterminal representing the extractor.
            capture_name: The capture name of the extractor, or `None` if the extractor does not capture.
            schema: The schema.
            to_object: A callable to convert the extracted string to a schema instance.
        """
        super().__init__(nonterminal, capture_name)
        self._to_object = to_object
        self._rule_str = _generate_kbnf_grammar(schema, self.nonterminal)
    def extract(self, input_str: str) -> typing.Optional[tuple[str, schemas.schema.Schema]]:
        """
        Extract a schema instance from a string.

        Args:
            input_str: The input string to extract from.

        Returns:
            A tuple of the remaining string and the extracted schema instance, or `None` if extraction failed.
        """

        # Ensure the input string starts with '{' or '[' after stripping leading whitespace
        input_str = input_str.lstrip()
        if not input_str.startswith(('{', '[')):
            return None

        # Variables to track the balance of brackets and the position in the string
        bracket_count = 0
        position = 0
        in_string = False
        escape_next = False
        start_char = input_str[0]
        end_char = '}' if start_char == '{' else ']'

        # Iterate over the string to find where the JSON object or array ends
        for char in input_str:
            if not in_string:
                if char == start_char:
                    bracket_count += 1
                elif char == end_char:
                    bracket_count -= 1
                elif char == '"':
                    in_string = True
            else:
                if char == '"' and not escape_next:
                    in_string = False
                elif char == '\\':
                    escape_next = not escape_next
                else:
                    escape_next = False

            # Move to the next character
            position += 1

            # If brackets are balanced and we're not in a string, stop processing
            if bracket_count == 0 and not in_string:
                break
        else:
            return None
        # The position now points to the character after the last '}', so we slice to position
        json_str = input_str[:position]
        remaining_str = input_str[position:]
        # Return the unparsed remainder of the string and the decoded JSON object
        return remaining_str, self._to_object(json_str)

    @property
    def kbnf_definition(self):
        return self._rule_str


_register_all_predefined_types()
