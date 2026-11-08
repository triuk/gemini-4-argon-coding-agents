"""Adapt JSON Schema unions and empty string literals for Gemini tools.

The original tool server still validates arguments against its original schema.
Only tool declarations are changed; messages and tool results are untouched.
"""
import json
from copy import deepcopy
from litellm.integrations.custom_logger import CustomLogger


def normalize(schema, root=False):
    if isinstance(schema, dict):
        # Vertex rejects empty enum strings. Keep the original values as guidance;
        # the tool server remains responsible for validating the exact constraint.
        values = schema.get('enum')
        if isinstance(values, list) and '' in values:
            schema.pop('enum')
            hint = 'Allowed values: ' + json.dumps(values, ensure_ascii=False) + '.'
            schema['description'] = (schema.get('description', '') + ' ' + hint).strip()
        if schema.get('const') == '':
            schema.pop('const')
            schema['description'] = (schema.get('description', '') + ' Must be the empty string.').strip()
        if 'oneOf' in schema and 'anyOf' not in schema:
            schema['anyOf'] = schema.pop('oneOf')
        if root and 'anyOf' in schema:
            branches = schema['anyOf']
            if branches and all(b.get('type', 'object') == 'object' for b in branches):
                properties = {}
                required = set(branches[0].get('required', []))
                for branch in branches:
                    required &= set(branch.get('required', []))
                    for key, value in branch.get('properties', {}).items():
                        if key not in properties:
                            properties[key] = value
                        elif properties[key] != value:
                            properties[key] = {'anyOf': [properties[key], value]}
                schema.pop('anyOf')
                schema.update(type='object', properties=properties)
                if required:
                    schema['required'] = sorted(required)
                else:
                    schema.pop('required', None)
        for value in schema.values():
            normalize(value)
    elif isinstance(schema, list):
        for value in schema:
            normalize(value)


class CodexHooks(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if data.get('tools'):
            data['tools'] = deepcopy(data['tools'])
            def visit(obj):
                if isinstance(obj, dict):
                    if isinstance(obj.get('parameters'), dict):
                        normalize(obj['parameters'], root=True)
                    for value in obj.values():
                        visit(value)
                elif isinstance(obj, list):
                    for value in obj:
                        visit(value)
            visit(data['tools'])
        return data


proxy_handler_instance = CodexHooks()
