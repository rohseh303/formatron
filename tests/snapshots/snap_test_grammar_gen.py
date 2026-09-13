# -*- coding: utf-8 -*-
# snapshottest: v1 - https://goo.gl/zC4yUc
from __future__ import unicode_literals

from snapshottest import Snapshot


snapshots = Snapshot()

snapshots['test_json_schema 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"name"\' colon start_name comma start_tail1;
start_tail1 ::= #'[ \t
]*"price"\' colon start_price comma start_tail2;
start_tail2 ::= #'[ \t
]*"tags"\' colon start_tags comma start_tail3 | start_tail3;
start_tail3 ::= #'[ \t
]*"inStock"\' colon start_inStock comma start_tail4 | start_tail4;
start_tail4 ::= #'[ \t
]*"category"\' colon start_category comma start_tail5;
start_tail5 ::= #'[ \t
]*"sku"\' colon start_sku;
start_sku ::= #'[ \t
]*"ITEM-001"\';
start_category ::= #'[ \t
]*"electronics"\' | #\'[ \t
]*114' | #'[ \t
]*514\\\\.1' | null | (array_begin start_category_4_0 comma start_category_4_1 comma start_category_4_2 comma start_category_4_3 array_end) | object_begin start_category_4_0 comma start_category_4_1 comma start_category_4_2 comma start_category_4_3 comma start_category_5_a comma start_category_5_b object_end;
start_category_5_b ::= #'[ \t
]*2\\\\.3';
start_category_5_a ::= #'[ \t
]*1';
start_category_4_3 ::= #'[ \t
]*true';
start_category_4_2 ::= #'[ \t
]*514\\\\.1';
start_category_4_1 ::= #'[ \t
]*514';
start_category_4_0 ::= #'[ \t
]*"114"\';
start_inStock ::= boolean;
start_tags ::= array_begin start_tags_item (comma start_tags_item)* array_end;
start_tags_item ::= start_tags_item_0 | start_tags_item_1;
start_tags_item_1 ::= number;
start_tags_item_0 ::= string;
start_price ::= #'[ \t
]*(?:0(?:\\\\.[0-9]+)?|(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_name ::= start_tags_item;
'''

snapshots['test_json_schema_array_min_max_items_constraints 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"min_items_array"\' colon start_min_items_array comma start_tail1;
start_tail1 ::= #'[ \t
]*"max_items_array"\' colon start_max_items_array comma start_tail2;
start_tail2 ::= #'[ \t
]*"min_max_items_array"\' colon start_min_max_items_array;
start_min_max_items_array ::= array_begin start_min_max_items_array_item start_min_max_items_array_item_more3 array_end;
start_min_max_items_array_item_more1 ::= (comma start_min_max_items_array_item)?;
start_min_max_items_array_item_more2 ::= (comma start_min_max_items_array_item start_min_max_items_array_item_more1)?;
start_min_max_items_array_item_more3 ::= (comma start_min_max_items_array_item start_min_max_items_array_item_more2)?;
start_min_max_items_array_item ::= boolean;
start_max_items_array ::= array_begin  array_end | array_begin start_max_items_array_item start_max_items_array_item_more2 array_end;
start_max_items_array_item_more1 ::= (comma start_max_items_array_item)?;
start_max_items_array_item_more2 ::= (comma start_max_items_array_item start_max_items_array_item_more1)?;
start_max_items_array_item ::= number;
start_min_items_array ::= array_begin start_min_items_array_item comma start_min_items_array_item (comma start_min_items_array_item)* array_end;
start_min_items_array_item ::= string;
'''

snapshots['test_json_schema_array_prefix_items 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"2_5_prefix_items"\' colon start_2_5_prefix_items comma start_tail1;
start_tail1 ::= #'[ \t
]*"1_4_prefix_items"\' colon start_1_4_prefix_items comma start_tail2;
start_tail2 ::= #'[ \t
]*"3__prefix_items"\' colon start_3__prefix_items comma start_tail3;
start_tail3 ::= #'[ \t
]*"0_4_prefix_items"\' colon start_0_4_prefix_items comma start_tail4;
start_tail4 ::= #'[ \t
]*"simple_prefix_items"\' colon start_simple_prefix_items;
start_simple_prefix_items ::= array_begin  array_end | array_begin start_simple_prefix_items_item_0 array_end | array_begin start_simple_prefix_items_item_0 (comma start_simple_prefix_items_item)* array_end;
start_simple_prefix_items_item ::= json_value;
start_simple_prefix_items_item_0 ::= string;
start_0_4_prefix_items ::= array_begin  array_end | array_begin start_0_4_prefix_items_item_0 array_end | array_begin start_0_4_prefix_items_item_0 start_0_4_prefix_items_item_more3 array_end;
start_0_4_prefix_items_item_more1 ::= (comma start_0_4_prefix_items_item)?;
start_0_4_prefix_items_item_more2 ::= (comma start_0_4_prefix_items_item start_0_4_prefix_items_item_more1)?;
start_0_4_prefix_items_item_more3 ::= (comma start_0_4_prefix_items_item start_0_4_prefix_items_item_more2)?;
start_0_4_prefix_items_item ::= json_value;
start_0_4_prefix_items_item_0 ::= string;
start_3__prefix_items ::= array_begin start_3__prefix_items_item_0 comma start_3__prefix_items_item_1 comma start_3__prefix_items_item (comma start_3__prefix_items_item)* array_end;
start_3__prefix_items_item ::= json_value;
start_3__prefix_items_item_1 ::= number;
start_3__prefix_items_item_0 ::= string;
start_1_4_prefix_items ::= array_begin start_1_4_prefix_items_item_0 array_end | array_begin start_1_4_prefix_items_item_0 comma start_1_4_prefix_items_item_1 array_end | array_begin start_1_4_prefix_items_item_0 comma start_1_4_prefix_items_item_1 start_1_4_prefix_items_item_more2 array_end;
start_1_4_prefix_items_item_more1 ::= (comma start_1_4_prefix_items_item)?;
start_1_4_prefix_items_item_more2 ::= (comma start_1_4_prefix_items_item start_1_4_prefix_items_item_more1)?;
start_1_4_prefix_items_item ::= boolean;
start_1_4_prefix_items_item_1 ::= number;
start_1_4_prefix_items_item_0 ::= string;
start_2_5_prefix_items ::= array_begin start_2_5_prefix_items_item_0 comma start_2_5_prefix_items_item_1 array_end | array_begin start_2_5_prefix_items_item_0 comma start_2_5_prefix_items_item_1 comma start_2_5_prefix_items_item_2 array_end;
start_2_5_prefix_items_item_2 ::= boolean;
start_2_5_prefix_items_item_1 ::= number;
start_2_5_prefix_items_item_0 ::= string;
'''

snapshots['test_json_schema_integer_constraints 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"gt_int"\' colon start_gt_int comma start_tail1;
start_tail1 ::= #'[ \t
]*"ge_int"\' colon start_ge_int comma start_tail2;
start_tail2 ::= #'[ \t
]*"lt_int"\' colon start_lt_int comma start_tail3;
start_tail3 ::= #'[ \t
]*"le_int"\' colon start_le_int;
start_le_int ::= #'[ \t
]*(?:-(?:[1-9]|[1-9][0-9]{1,})|0)';
start_lt_int ::= #'[ \t
]*(?:-(?:[1-9]|[1-9][0-9]{1,}))';
start_ge_int ::= #'[ \t
]*(?:0|(?:[1-9]|[1-9][0-9]{1,}))';
start_gt_int ::= #'[ \t
]*(?:(?:[1-9]|[1-9][0-9]{1,}))';
'''

snapshots['test_json_schema_number_constraints 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"gt_number"\' colon start_gt_number comma start_tail1;
start_tail1 ::= #'[ \t
]*"ge_number"\' colon start_ge_number comma start_tail2;
start_tail2 ::= #'[ \t
]*"lt_number"\' colon start_lt_number comma start_tail3;
start_tail3 ::= #'[ \t
]*"le_number"\' colon start_le_number;
start_le_number ::= #'[ \t
]*(?:-0\\\\.[0-9]*[1-9][0-9]*|-(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?|0(?:\\\\.0+)?)';
start_lt_number ::= #'[ \t
]*(?:-0\\\\.[0-9]*[1-9][0-9]*|-(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_ge_number ::= #'[ \t
]*(?:0(?:\\\\.[0-9]+)?|(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_gt_number ::= #'[ \t
]*(?:0\\\\.[0-9]*[1-9][0-9]*|(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
'''

snapshots['test_json_schema_object_without_properties 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object;
'''

snapshots['test_json_schema_substring_constraint 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"substring_str"\' colon start_substring_str;
start_substring_str ::= #'[ \t
]*\' \'"\' #substrs\'Hello, world!\' \'"\';
'''

snapshots['test_pydantic_callable 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"a"\' colon start_a (comma start_tail1)?;
start_tail1 ::= #'[ \t
]*"b"\' colon start_b;
start_b ::= integer;
start_a ::= integer;
'''

snapshots['test_pydantic_class 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"a"\' colon start_a comma start_tail1 | start_tail1;
start_tail1 ::= #'[ \t
]*"b"\' colon start_b comma start_tail2 | start_tail2;
start_tail2 ::= #'[ \t
]*"c"\' colon start_c comma start_tail3;
start_tail3 ::= #'[ \t
]*"e"\' colon start_e comma start_tail4;
start_tail4 ::= #'[ \t
]*"f"\' colon start_f;
start_f ::= start_f_0 | start_f_1 | start_f_2 | start_f_3 | start_f_4;
start_f_4 ::= array_begin (start_f_4_value (comma start_f_4_value)*)? array_end;
start_f_4_value ::= integer;
start_f_3 ::= integer;
start_f_2 ::= json_value;
start_f_1 ::= integer;
start_f_0 ::= boolean;
start_e ::=array_begin start_e_0 comma start_e_1 comma start_e_2 comma start_e_3 comma start_e_4 array_end;
start_e_4 ::= object;
start_e_3 ::= object;
start_e_2 ::= number;
start_e_1 ::= string;
start_e_0 ::= array_begin (start_e_0_value (comma start_e_0_value)*)? array_end;
start_e_0_value ::= number;
start_c ::= #'[ \t
]*"114\\\'\\\\\\\\""\' | #\'[ \t
]*"514"\' | #\'[ \t
]*true' | #'[ \t
]*"1919"\' | #\'[ \t
]*"810"\';
start_b ::= integer;
start_a ::= string;
'''

snapshots['test_pydantic_class_linked_list 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"value"\' colon start_value comma start_tail1;
start_tail1 ::= #'[ \t
]*"next"\' colon start_next;
start_next ::= start_next_0 | start_next_1;
start_next_1 ::= null;
start_next_0 ::= start;
start_value ::= integer;
'''

snapshots['test_pydantic_float_constraints 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"gt_float"\' colon start_gt_float comma start_tail1;
start_tail1 ::= #'[ \t
]*"ge_float"\' colon start_ge_float comma start_tail2;
start_tail2 ::= #'[ \t
]*"lt_float"\' colon start_lt_float comma start_tail3;
start_tail3 ::= #'[ \t
]*"le_float"\' colon start_le_float comma start_tail4;
start_tail4 ::= #'[ \t
]*"positive_float"\' colon start_positive_float comma start_tail5;
start_tail5 ::= #'[ \t
]*"negative_float"\' colon start_negative_float comma start_tail6;
start_tail6 ::= #'[ \t
]*"nonnegative_float"\' colon start_nonnegative_float comma start_tail7;
start_tail7 ::= #'[ \t
]*"nonpositive_float"\' colon start_nonpositive_float;
start_nonpositive_float ::= #'[ \t
]*(?:-0\\\\.[0-9]*[1-9][0-9]*|-(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?|0(?:\\\\.0+)?)';
start_nonnegative_float ::= #'[ \t
]*(?:0(?:\\\\.[0-9]+)?|(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_negative_float ::= #'[ \t
]*(?:-0\\\\.[0-9]*[1-9][0-9]*|-(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_positive_float ::= #'[ \t
]*(?:0\\\\.[0-9]*[1-9][0-9]*|(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_le_float ::= #'[ \t
]*(?:-0\\\\.[0-9]*[1-9][0-9]*|-(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?|0(?:\\\\.0+)?)';
start_lt_float ::= #'[ \t
]*(?:-0\\\\.[0-9]*[1-9][0-9]*|-(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_ge_float ::= #'[ \t
]*(?:0(?:\\\\.[0-9]+)?|(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
start_gt_float ::= #'[ \t
]*(?:0\\\\.[0-9]*[1-9][0-9]*|(?:[1-9]|[1-9][0-9]{1,})(?:\\\\.[0-9]+)?)';
'''

snapshots['test_pydantic_integer_constraints 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"gt_int"\' colon start_gt_int comma start_tail1;
start_tail1 ::= #'[ \t
]*"ge_int"\' colon start_ge_int comma start_tail2;
start_tail2 ::= #'[ \t
]*"lt_int"\' colon start_lt_int comma start_tail3;
start_tail3 ::= #'[ \t
]*"le_int"\' colon start_le_int comma start_tail4;
start_tail4 ::= #'[ \t
]*"positive_int"\' colon start_positive_int comma start_tail5;
start_tail5 ::= #'[ \t
]*"negative_int"\' colon start_negative_int comma start_tail6;
start_tail6 ::= #'[ \t
]*"nonnegative_int"\' colon start_nonnegative_int comma start_tail7;
start_tail7 ::= #'[ \t
]*"nonpositive_int"\' colon start_nonpositive_int;
start_nonpositive_int ::= #'[ \t
]*(?:-(?:[1-9]|[1-9][0-9]{1,})|0)';
start_nonnegative_int ::= #'[ \t
]*(?:0|(?:[1-9]|[1-9][0-9]{1,}))';
start_negative_int ::= #'[ \t
]*(?:-(?:[1-9]|[1-9][0-9]{1,}))';
start_positive_int ::= #'[ \t
]*(?:(?:[1-9]|[1-9][0-9]{1,}))';
start_le_int ::= #'[ \t
]*(?:-(?:[1-9]|[1-9][0-9]{1,})|0)';
start_lt_int ::= #'[ \t
]*(?:-(?:[1-9]|[1-9][0-9]{1,}))';
start_ge_int ::= #'[ \t
]*(?:0|(?:[1-9]|[1-9][0-9]{1,}))';
start_gt_int ::= #'[ \t
]*(?:(?:[1-9]|[1-9][0-9]{1,}))';
'''

snapshots['test_pydantic_sequence_constraints 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"min_2_list"\' colon start_min_2_list comma start_tail1;
start_tail1 ::= #'[ \t
]*"max_5_list"\' colon start_max_5_list comma start_tail2;
start_tail2 ::= #'[ \t
]*"min_1_max_3_list"\' colon start_min_1_max_3_list comma start_tail3;
start_tail3 ::= #'[ \t
]*"min_2_tuple"\' colon start_min_2_tuple comma start_tail4;
start_tail4 ::= #'[ \t
]*"max_5_tuple"\' colon start_max_5_tuple comma start_tail5;
start_tail5 ::= #'[ \t
]*"min_1_max_3_tuple"\' colon start_min_1_max_3_tuple comma start_tail6;
start_tail6 ::= #'[ \t
]*"empty_list"\' colon start_empty_list;
start_empty_list ::= array_begin  array_end | array_begin start_empty_list_item (comma start_empty_list_item)* array_end;
start_empty_list_item ::= json_value;
start_min_1_max_3_tuple ::= array_begin start_min_1_max_3_tuple_item start_min_1_max_3_tuple_item_more2 array_end;
start_min_1_max_3_tuple_item_more1 ::= (comma start_min_1_max_3_tuple_item)?;
start_min_1_max_3_tuple_item_more2 ::= (comma start_min_1_max_3_tuple_item start_min_1_max_3_tuple_item_more1)?;
start_min_1_max_3_tuple_item ::= number;
start_max_5_tuple ::= array_begin  array_end | array_begin start_max_5_tuple_item start_max_5_tuple_item_more4 array_end;
start_max_5_tuple_item_more1 ::= (comma start_max_5_tuple_item)?;
start_max_5_tuple_item_more2 ::= (comma start_max_5_tuple_item start_max_5_tuple_item_more1)?;
start_max_5_tuple_item_more3 ::= (comma start_max_5_tuple_item start_max_5_tuple_item_more2)?;
start_max_5_tuple_item_more4 ::= (comma start_max_5_tuple_item start_max_5_tuple_item_more3)?;
start_max_5_tuple_item ::= string;
start_min_2_tuple ::= array_begin start_min_2_tuple_item comma start_min_2_tuple_item (comma start_min_2_tuple_item)* array_end;
start_min_2_tuple_item ::= integer;
start_min_1_max_3_list ::= array_begin start_min_1_max_3_list_item start_min_1_max_3_list_item_more2 array_end;
start_min_1_max_3_list_item_more1 ::= (comma start_min_1_max_3_list_item)?;
start_min_1_max_3_list_item_more2 ::= (comma start_min_1_max_3_list_item start_min_1_max_3_list_item_more1)?;
start_min_1_max_3_list_item ::= number;
start_max_5_list ::= array_begin  array_end | array_begin start_max_5_list_item start_max_5_list_item_more4 array_end;
start_max_5_list_item_more1 ::= (comma start_max_5_list_item)?;
start_max_5_list_item_more2 ::= (comma start_max_5_list_item start_max_5_list_item_more1)?;
start_max_5_list_item_more3 ::= (comma start_max_5_list_item start_max_5_list_item_more2)?;
start_max_5_list_item_more4 ::= (comma start_max_5_list_item start_max_5_list_item_more3)?;
start_max_5_list_item ::= string;
start_min_2_list ::= array_begin start_min_2_list_item comma start_min_2_list_item (comma start_min_2_list_item)* array_end;
start_min_2_list_item ::= integer;
'''

snapshots['test_pydantic_string_constraints 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"min_length_str"\' colon start_min_length_str comma start_tail1;
start_tail1 ::= #'[ \t
]*"max_length_str"\' colon start_max_length_str comma start_tail2;
start_tail2 ::= #'[ \t
]*"pattern_str"\' colon start_pattern_str comma start_tail3;
start_tail3 ::= #'[ \t
]*"combined_str"\' colon start_combined_str;
start_combined_str ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt/]|\\\\\\\\u[0-9A-Fa-f]{4}){2,5}"\';
start_pattern_str ::= #'[ \t
]*"(?:[a-zA-Z0-9]+)"\';
start_max_length_str ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt/]|\\\\\\\\u[0-9A-Fa-f]{4}){0,10}"\';
start_min_length_str ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt/]|\\\\\\\\u[0-9A-Fa-f]{4}){3,}"\';
'''

snapshots['test_pydantic_substring_constraint 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"substring_str"\' colon start_substring_str;
start_substring_str ::= string;
'''

snapshots['test_recursive_binary_tree_schema 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"value"\' colon start_value (comma start_tail1)?;
start_tail1 ::= #'[ \t
]*"left"\' colon start_left (comma start_tail2)? | start_tail2;
start_tail2 ::= #'[ \t
]*"right"\' colon start_right;
start_right ::= object_begin start_right_tail0 object_end;
start_right_tail0 ::= #'[ \t
]*"value"\' colon start_right_value (comma start_right_tail1)?;
start_right_tail1 ::= #'[ \t
]*"left"\' colon start_right_left (comma start_right_tail2)? | start_right_tail2;
start_right_tail2 ::= #'[ \t
]*"right"\' colon start_right_right;
start_right_right ::= start_right;
start_right_left ::= object_begin start_right_left_tail0 object_end;
start_right_left_tail0 ::= #'[ \t
]*"value"\' colon start_right_left_value (comma start_right_left_tail1)?;
start_right_left_tail1 ::= #'[ \t
]*"left"\' colon start_right_left_left (comma start_right_left_tail2)? | start_right_left_tail2;
start_right_left_tail2 ::= #'[ \t
]*"right"\' colon start_right_left_right;
start_right_left_right ::= start_right;
start_right_left_left ::= start_right_left;
start_right_left_value ::= number;
start_right_value ::= number;
start_left ::= start_right_left;
start_value ::= number;
'''

snapshots['test_recursive_linked_list_schema 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"value"\' colon start_value (comma start_tail1)?;
start_tail1 ::= #'[ \t
]*"next"\' colon start_next;
start_next ::= object_begin start_next_tail0 object_end;
start_next_tail0 ::= #'[ \t
]*"value"\' colon start_next_value (comma start_next_tail1)?;
start_next_tail1 ::= #'[ \t
]*"next"\' colon start_next_next;
start_next_next ::= start_next;
start_next_value ::= integer;
start_value ::= integer;
'''

snapshots['test_schema_with_anchor_reference 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"mainProperty"\' colon start_mainProperty comma start_tail1;
start_tail1 ::= #'[ \t
]*"referencedObject"\' colon start_referencedObject comma start_tail2;
start_tail2 ::= #'[ \t
]*"referencedObject2"\' colon start_referencedObject2;
start_referencedObject2 ::= object_begin start_referencedObject2_tail0 object_end;
start_referencedObject2_tail0 ::= #'[ \t
]*"subProperty"\' colon start_referencedObject2_subProperty;
start_referencedObject2_subProperty ::= integer;
start_referencedObject ::= object_begin start_referencedObject_tail0 object_end;
start_referencedObject_tail0 ::= #'[ \t
]*"subProperty"\' colon start_referencedObject_subProperty;
start_referencedObject_subProperty ::= integer;
start_mainProperty ::= string;
'''

snapshots['test_schema_with_anyOf_inside_array 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"items"\' colon start_items;
start_items ::= array_begin (start_items_value (comma start_items_value)*)? array_end;
start_items_value ::= start_items_value_0 | start_items_value_1 | start_items_value_2;
start_items_value_2 ::= boolean;
start_items_value_1 ::= object_begin start_items_value_1_tail0 object_end;
start_items_value_1_tail0 ::= #'[ \t
]*"name"\' colon start_items_value_1_name comma start_items_value_1_tail1;
start_items_value_1_tail1 ::= #'[ \t
]*"value"\' colon start_items_value_1_value;
start_items_value_1_value ::= number;
start_items_value_1_name ::= string;
start_items_value_0 ::= string;
'''

snapshots['test_schema_with_dynamic_ref 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0? object_end;
start_tail0 ::= #'[ \t
]*"data"\' colon start_data (comma start_tail1)? | start_tail1;
start_tail1 ::= #'[ \t
]*"children"\' colon start_children (comma start_tail2)? | start_tail2;
start_tail2 ::= #'[ \t
]*"metadata"\' colon start_metadata;
start_metadata ::= string;
start_children ::= array_begin (start_children_value (comma start_children_value)*)? array_end;
start_children_value ::= object_begin start_children_value_tail0? object_end;
start_children_value_tail0 ::= #'[ \t
]*"data"\' colon start_children_value_data (comma start_children_value_tail1)? | start_children_value_tail1;
start_children_value_tail1 ::= #'[ \t
]*"children"\' colon start_children_value_children (comma start_children_value_tail2)? | start_children_value_tail2;
start_children_value_tail2 ::= #'[ \t
]*"metadata"\' colon start_children_value_metadata;
start_children_value_metadata ::= string;
start_children_value_children ::= array_begin (start_children_value_children_value (comma start_children_value_children_value)*)? array_end;
start_children_value_children_value ::= object_begin start_children_value_children_value_tail0? object_end;
start_children_value_children_value_tail0 ::= #'[ \t
]*"data"\' colon start_children_value_children_value_data (comma start_children_value_children_value_tail1)? | start_children_value_children_value_tail1;
start_children_value_children_value_tail1 ::= #'[ \t
]*"children"\' colon start_children_value_children_value_children (comma start_children_value_children_value_tail2)? | start_children_value_children_value_tail2;
start_children_value_children_value_tail2 ::= #'[ \t
]*"metadata"\' colon start_children_value_children_value_metadata;
start_children_value_children_value_metadata ::= string;
start_children_value_children_value_children ::= array_begin (start_children_value_children_value_children_value (comma start_children_value_children_value_children_value)*)? array_end;
start_children_value_children_value_children_value ::= start_children_value_children_value;
start_children_value_children_value_data ::= string;
start_children_value_data ::= string;
start_data ::= string;
'''

snapshots['test_schema_with_embedded_schema 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"referencedEmbedded"\' colon start_referencedEmbedded;
start_referencedEmbedded ::= object_begin start_referencedEmbedded_tail0 object_end;
start_referencedEmbedded_tail0 ::= #'[ \t
]*"embeddedProperty"\' colon start_referencedEmbedded_embeddedProperty;
start_referencedEmbedded_embeddedProperty ::= integer;
'''

snapshots['test_schema_with_reference 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"name"\' colon start_name comma start_tail1;
start_tail1 ::= #'[ \t
]*"age"\' colon start_age comma start_tail2;
start_tail2 ::= #'[ \t
]*"address"\' colon start_address;
start_address ::= object_begin start_address_tail0 object_end;
start_address_tail0 ::= #'[ \t
]*"street"\' colon start_address_street comma start_address_tail1;
start_address_tail1 ::= #'[ \t
]*"city"\' colon start_address_city comma start_address_tail2;
start_address_tail2 ::= #'[ \t
]*"country"\' colon start_address_country;
start_address_country ::= string;
start_address_city ::= string;
start_address_street ::= string;
start_age ::= integer;
start_name ::= string;
'''

snapshots['test_schema_with_reference_to_number 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"mainProperty"\' colon start_mainProperty comma start_tail1;
start_tail1 ::= #'[ \t
]*"numberReference"\' colon start_numberReference;
start_numberReference ::= #'[ \t
]*(?:0(?:\\\\.[0-9]+)?|(?:[1-9]|(?:1[0-9]|[2-8][0-9]|9[0-9]))(?:\\\\.[0-9]+)?|100(?:\\\\.0+)?)';
start_mainProperty ::= string;
'''

snapshots['test_schema_with_string_metadata 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= object_begin start_tail0 object_end;
start_tail0 ::= #'[ \t
]*"username"\' colon start_username comma start_tail1;
start_tail1 ::= #'[ \t
]*"email"\' colon start_email comma start_tail2;
start_tail2 ::= #'[ \t
]*"description"\' colon start_description comma start_tail3;
start_tail3 ::= #'[ \t
]*"password"\' colon start_password;
start_password ::= #'[ \t
]*"(?:(?:[^"\\\\\\\\\\\\x00-\\\\x1f]|\\\\\\\\["\\\\\\\\/bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*[A-Za-z](?:[^"\\\\\\\\\\\\x00-\\\\x1f]|\\\\\\\\["\\\\\\\\/bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*)"\';
start_description ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt/]|\\\\\\\\u[0-9A-Fa-f]{4}){0,200}"\';
start_email ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt/]|\\\\\\\\u[0-9A-Fa-f]{4}){3,}"\';
start_username ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt/]|\\\\\\\\u[0-9A-Fa-f]{4}){3,20}"\';
'''

snapshots['test_schema_with_top_level_anyOf 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= start_0 | start_1 | start_2;
start_2 ::= string;
start_1 ::= array_begin (start_1_value (comma start_1_value)*)? array_end;
start_1_value ::= string;
start_0 ::= object_begin start_0_tail0 object_end;
start_0_tail0 ::= #'[ \t
]*"name"\' colon start_0_name comma start_0_tail1;
start_0_tail1 ::= #'[ \t
]*"age"\' colon start_0_age;
start_0_age ::= integer;
start_0_name ::= string;
'''

snapshots['test_schema_with_top_level_array 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= array_begin start_item (comma start_item)* array_end;
start_item ::= object_begin start_item_tail0 object_end;
start_item_tail0 ::= #'[ \t
]*"id"\' colon start_item_id comma start_item_tail1;
start_item_tail1 ::= #'[ \t
]*"name"\' colon start_item_name (comma start_item_tail2)?;
start_item_tail2 ::= #'[ \t
]*"active"\' colon start_item_active;
start_item_active ::= boolean;
start_item_name ::= string;
start_item_id ::= integer;
'''

snapshots['test_schema_with_union_array_object 1'] = '''integer ::= #"[ \t
]*-?(0|[1-9][0-9]*)";
number ::= #"[ \t
]*-?(0|[1-9][0-9]*)(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?";
string ::= #'[ \t
]*"([^\\\\\\\\"\\u0000-\\u001f]|\\\\\\\\["\\\\\\\\bfnrt]|\\\\\\\\u[0-9A-Fa-f]{4})*"\';
boolean ::= #"[ \t
]*(true|false)";
null ::= #"[ \t
]*null";
array ::= array_begin (json_value (comma json_value)*)? array_end;
object ::= object_begin (string colon json_value (comma string colon json_value)*)? object_end;
json_value ::= number|string|boolean|null|array|object;
comma ::= #"[ \t
]*,";
colon ::= #"[ \t
]*:";
object_begin ::= #"[ \t
]*\\\\{";
object_end ::= #"[ \t
]*\\\\}";
array_begin ::= #"[ \t
]*\\\\[";
array_end ::= #"[ \t
]*\\\\]";
start ::= start_0 | start_1;
start_1 ::= object_begin start_1_tail0 object_end;
start_1_tail0 ::= #'[ \t
]*"name"\' colon start_1_name (comma start_1_tail1)?;
start_1_tail1 ::= #'[ \t
]*"age"\' colon start_1_age;
start_1_age ::= integer;
start_1_name ::= string;
start_0 ::= array_begin (start_0_value (comma start_0_value)*)? array_end;
start_0_value ::= string;
'''
