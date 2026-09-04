# Codex CLI install

Everstate does not bundle or proxy Codex. For the native Ubuntu continuity test, install the official OpenAI Codex CLI separately:

```bash
npm i -g @openai/codex
codex --version
```

Then run `codex` once and complete its normal sign-in flow before using `everstate switch codex`.

See OpenAI's official Codex documentation/product page for current availability and account requirements.
