---
globs: ["**/test_*.py", "**/*_test.py"]
---

# Testing Rules

- Use `pytest` for all tests.
- Group related tests in classes prefixed with `Test`.
- Use `assert` statements directly — no unittest-style `self.assert*`.
- Test both success and failure paths.
- Use Pydantic's `model_validate` for success and catch `ValidationError` for failures.
- Use static fixture files in `src/config/fixtures/` for config tests — do not dynamically create/delete files.
- Mock only at system boundaries (subprocess calls, network, filesystem when testing in-memory logic).
- Test external behavior, not implementation details.
- Write tests as vertical slices — each test exercises a full path through the system.
