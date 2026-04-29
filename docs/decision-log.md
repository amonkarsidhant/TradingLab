# Decision Log

| Date | Decision | Reason | Risk | Revisit Date |
|---|---|---|---|---|
| Day 0 | Use demo-only Trading 212 environment | Learn safely before risking capital | False confidence from demo results | Day 30 |
| Day 0 | Use Claude Code as primary coding tool | Best fit for repo-based iterative coding | May generate unsafe changes if instructions are weak | Weekly |
| Day 0 | Use ChatGPT as sparring/review layer | Strong for architecture and critique | May over-strategize without execution | Weekly |
| Day 0 | Use Ollama for local/cloud experiments | Useful for low-cost repeated summaries | Model quality varies | Weekly |
| Day 1 | Confirmed T212 demo API connectivity | account-summary, positions, fetch-instruments all return valid data (€5,000 demo balance, 15,357 instruments) | None — read-only demo calls only | Day 7 |
| Day 1 | Add pip install -e . to setup | python -m trading_lab.cli failed without editable install; PYTHONPATH=src workaround is fragile | None | Day 30 |
