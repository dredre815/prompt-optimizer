"""Engineering-only patch for confirmation run.
Changes no scientific parameter. It only raises DeepSeek final output token budget
from 120 to 512 to avoid empty final content observed in Run 1.
"""
try:
    from openai.resources.chat.completions.completions import Completions
    _orig_create = Completions.create
    def _patched_create(self, *args, **kwargs):
        if kwargs.get('model') == 'deepseek-v4-flash' and kwargs.get('max_tokens') == 120:
            kwargs['max_tokens'] = 512
        return _orig_create(self, *args, **kwargs)
    Completions.create = _patched_create
    print('TRADELEAK_ENGINEERING_PATCH=max_tokens_512', flush=True)
except Exception as exc:
    print('TRADELEAK_ENGINEERING_PATCH_FAILED=' + type(exc).__name__ + ':' + str(exc), flush=True)
