# Second-Pass Cleaning Todo

- [x] Inspect current LLM review pipeline and confirm low-confidence item ids are not persisted by the original script.
- [x] Decide on a new independent second-pass flow that leaves the original script untouched.
- [x] Implement a new second-pass review service that reruns low-confidence single-item candidates locally.
- [x] Add a new CLI command for the second-pass cleaner with separate output, usage, and unresolved-low-confidence files.
- [x] Run unit tests for the new flow.
- [x] Run a small live smoke test with the local model.
- [ ] Decide whether to switch the production cleaning job to the new second-pass script after validation.

## Self-check Notes

- Original `review-items-llm` semantics must stay unchanged.
- Second-pass script should prioritize reliability over token cost.
- Low-confidence items that still fail second-pass should be explicitly persisted for later analysis instead of disappearing.
