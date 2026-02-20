[
    [
        'k] = f"<{len(v)} chars>',
        'elif isinstance(v, list) and len(v) > 10:\n                    clean[k] = v[:10] + [f"... +{len(v) - 10}',
    ],
    [2000],
    [
        'k] = self._context_guard.compress(v)\n                    elif len(v) > 500:\n                        clean[k] = f"<{len(v)} chars>',
        'elif isinstance(v, list) and len(v) > 10:\n                    clean[k] = v[:10] + [f"... +{len(v) - 10}',
    ],
    [2000],
    [
        'Dict]) -> Tuple[bool, Optional[str]]:\n        "',
        'Check context status and trim if necessary."',
        '\n        status = self._context_guard.get_status(messages)\n        \n        if status == ContextStatus.OVERFLOW:\n            return False, f"Context overflow: {self._context_guard.stats.total_tokens_used} tokens"\n        elif status == ContextStatus.CRITICAL:\n            log.warning(f"Context critical: {self._context_guard.stats.total_tokens_used} tokens")\n        elif status == ContextStatus.WARNING:\n            log.info(f"Context warning: {self._context_guard.stats.total_tokens_used} tokens',
        "return True, None'''\n\ncontent = content.replace(old_text, new_text)\n\nwith open('agent/base_agent.py', 'w') as f:\n    f.write(content)\n\nprint('Done')",
    ],
]
