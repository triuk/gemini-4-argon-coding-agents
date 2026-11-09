import asyncio
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import unittest

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
from litellm.llms.vertex_ai.common_utils import build_vertex_schema
from litellm.responses.litellm_completion_transformation.custom_tools import convert_custom_tool_to_function_tool


spec = importlib.util.spec_from_file_location(
    "argon_hooks", Path(__file__).resolve().parents[1] / "proxy/argon_hooks.py"
)
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)


def converted(schema):
    data = {"tools": [{"type": "function", "name": "sample", "parameters": schema}]}
    result = asyncio.run(hooks.proxy_handler_instance.async_pre_call_hook(None, None, data, "responses"))
    return result["tools"][0]["parameters"]


class SchemaTests(unittest.TestCase):
    def test_nested_empty_enum_survives_real_litellm_conversion(self):
        schema = {"type": "object", "properties": {"query": {"anyOf": [
            {"type": "string"}, {"type": "string", "enum": [""]}
        ]}}}
        result = build_vertex_schema(converted(schema))
        branch = result["properties"]["query"]["anyOf"][1]
        self.assertNotIn("enum", branch)
        self.assertIn('[""]', branch["description"])
        self.assertEqual(schema["properties"]["query"]["anyOf"][1]["enum"], [""])

    def test_mixed_enum_retains_values_as_guidance(self):
        result = converted({"type": "string", "enum": ["", "a"], "description": "A choice."})
        self.assertNotIn("enum", result)
        self.assertIn('A choice. Allowed values: ["", "a"].', result["description"])

    def test_normal_enums_stay_restricted(self):
        schema = {"type": "object", "properties": {"mode": {"type": "string", "enum": ["a", "b"]}}}
        self.assertEqual(converted(schema), schema)

    def test_empty_const(self):
        result = build_vertex_schema(converted({"type": "string", "const": ""}))
        self.assertNotIn("enum", result)
        self.assertIn("empty string", result["description"])

    def test_nested_oneof(self):
        schema = {"type": "object", "properties": {"target": {"oneOf": [
            {"type": "string"}, {"type": "object", "properties": {"id": {"type": "string"}}}
        ]}}}
        result = build_vertex_schema(converted(schema))
        self.assertEqual(len(result["properties"]["target"]["anyOf"]), 2)

    def test_root_union_keeps_common_required_fields(self):
        schema = {"oneOf": [
            {"type": "object", "properties": {"id": {"type": "string"}, "code": {"type": "string"}}, "required": ["id", "code"]},
            {"type": "object", "properties": {"id": {"type": "string"}, "summary": {"type": "string"}}, "required": ["id", "summary"]},
        ]}
        result = build_vertex_schema(converted(schema))
        self.assertEqual(result["type"], "object")
        self.assertEqual(result["required"], ["id"])
        self.assertEqual(set(result["properties"]), {"id", "code", "summary"})

    def test_root_union_without_common_required_fields(self):
        result = converted({"oneOf": [
            {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
        ]})
        self.assertNotIn("required", result)
        self.assertNotIn("anyOf", result)

    def test_root_union_preserves_different_property_types(self):
        result = converted({"anyOf": [
            {"type": "object", "properties": {"value": {"type": "string"}}},
            {"type": "object", "properties": {"value": {"type": "number"}}},
        ]})
        self.assertEqual(len(result["properties"]["value"]["anyOf"]), 2)

    def test_hook_changes_only_copied_declarations(self):
        tools = [{"type": "function", "function": {"name": "echo", "parameters": {
            "type": "object", "properties": {"text": {"type": "string", "enum": [""]}}
        }}}]
        data = {"tools": tools, "input": [{"content": {"enum": [""]}}], "instructions": "keep"}
        before = deepcopy(data)
        result = asyncio.run(hooks.proxy_handler_instance.async_pre_call_hook(None, None, data, "responses"))
        self.assertEqual(tools, before["tools"])
        self.assertIsNot(result["tools"], tools)
        self.assertEqual(result["input"], before["input"])
        self.assertEqual(result["instructions"], "keep")

    def test_large_code_mode_catalog_is_preserved_in_instructions(self):
        catalog = '\n'.join(f'tools.fixture_{number}(text: string): Promise<string>;' for number in range(600))
        tools = [{"type": "custom", "name": "exec", "description": catalog}]
        data = {"tools": tools, "instructions": "existing instructions", "input": [{"role": "user", "content": "keep"}]}
        before = deepcopy(data)
        result = asyncio.run(hooks.proxy_handler_instance.async_pre_call_hook(None, None, data, "aresponses"))
        self.assertLessEqual(len(result['tools'][0]['description'].encode('utf-8')), hooks.DESCRIPTION_BUDGET)
        bridged = convert_custom_tool_to_function_tool(result['tools'][0])
        self.assertLessEqual(len(bridged['function']['description'].encode('utf-8')), hooks.DESCRIPTION_BUDGET)
        self.assertIn(catalog, result['instructions'])
        self.assertTrue(result['instructions'].startswith('existing instructions'))
        self.assertEqual(tools, before['tools'])
        self.assertEqual(result['input'], before['input'])
        again = asyncio.run(hooks.proxy_handler_instance.async_pre_call_hook(None, None, result, "responses"))
        self.assertEqual(again['instructions'].count(catalog), 1)

    def test_nested_tool_guidance_keeps_names_and_unicode_without_truncation(self):
        description = '\u017e' * 800  # UTF-8 byte budget, not just ASCII character count.
        data = {"tools": [{"type": "namespace", "name": "fixture", "tools": [
            {"type": "function", "name": "echo", "description": description,
             "parameters": {"type": "object", "properties": {}}}]}]}
        result = asyncio.run(hooks.proxy_handler_instance.async_pre_call_hook(None, None, data, "responses"))
        self.assertIn('## Tool fixture.echo\n\n' + description, result['instructions'])
        converted = build_vertex_schema(result['tools'][0]['tools'][0]['parameters'])
        self.assertEqual(converted['type'], 'object')


if __name__ == "__main__":
    unittest.main()
