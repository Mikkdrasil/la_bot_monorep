import inspect
from pathlib import Path

import pytest


@pytest.mark.skip(reason='Использовалось для генерации тест-кейсов')
def test_generate_cases():
    import communicate.main

    _generate_test_cases(communicate.main, 'communicate', 'tests/test_communicate_generated.py')


@pytest.mark.skip(reason='Использовалось для генерации тест-кейсов')
def test_generate_all_cases():
    dir_names = [x.name for x in Path('src').glob('*')]
    dir_names.sort()
    print('')
    for dir_name in dir_names:
        print(f'import {dir_name}.main')
        print(f"generate_test_cases( {dir_name}.main, '{dir_name}', 'tests/test_{dir_name}_generated.py')")
        print('')


@pytest.mark.skip(reason='Использовалось для генерации тест-кейсов')
def test_gen():
    """copy output of test_generate_all_cases and run to generate smoke test templates"""
    pass


def _generate_test_cases(module, module_name: str, res_filename: str) -> str:
    template = """
def test_{func_name}():
    from {module_name}.main import {func_name}
    res = {func_name}({args})
    pass
        
    """

    testcases = []
    members = inspect.getmembers(module)
    for member in members:
        if not inspect.isfunction(member[1]):
            continue

        signature = inspect.signature(member[1])
        args_str = ', '.join([f'{arg}=MagicMock()' for arg in signature.parameters])

        testcase = template.format(module_name=module_name, func_name=member[0], args=args_str)
        testcases.append(testcase)

    testcases.insert(0, 'from unittest.mock import MagicMock')

    Path(res_filename).write_text('\n'.join(testcases))
    return '\n'.join(testcases)
