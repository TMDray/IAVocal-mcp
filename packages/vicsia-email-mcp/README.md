# vicsia-email-mcp (DEPRECATED)

This package has been split into two dedicated packages since v0.3.0:

- **Gmail users** → install [`vicsia-gmail-mcp`](https://pypi.org/project/vicsia-gmail-mcp/)
- **Outlook users** → install [`vicsia-outlook-mcp`](https://pypi.org/project/vicsia-outlook-mcp/)

Reasons for the split: independent dependencies, independent release cycles, no more `EMAIL_PROVIDER` env switch.

Vicsia users get the migration automatically via the next app update — no action required.

The last functional version of this unified package is `0.2.1`. After v0.3.0, this entry point only prints a deprecation notice and exits.
