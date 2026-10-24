# Singapore iPhone Duo pickup monitor

Unofficial monitor for Apple's Singapore pickup availability. It watches:
- Star White: 256GB, 512GB, 1TB
- Night Sky: 256GB, 512GB, 1TB
- Apple Orchard Road, Apple Marina Bay Sands, Apple Jewel Changi Airport

It sends a Telegram message when a configuration changes to available. The
first successful run also alerts for any items already available.

## Install

1. Copy `monitor.py`, `state.json`, and `.github/workflows/monitor.yml` into the
   root of your GitHub repository, preserving the `.github/workflows` folders.
2. Confirm repository secrets exist:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. In GitHub, open **Actions** and enable workflows if prompted.
4. Select **Singapore iPhone Duo pickup monitor** → **Run workflow** → choose
   `test` → **Run workflow**. Confirm the Telegram message arrives.
5. Run it again with mode `check` to make an initial stock check. The scheduled
   workflow then targets every 10 minutes.

## Notes and limitations

- GitHub scheduled workflows may start late; ten minutes is a target, not a
  guarantee. Schedules use UTC, but this interval is timezone-independent.
- Apple's pickup endpoint is undocumented and can change or rate-limit requests.
  The script stops with an error if the response is unexpected or a requested
  store/configuration is missing. It does not interpret API failures as "out of stock".
- The script makes three Apple requests per scheduled run, one per Singapore
  store postal code, with all six part numbers included in each request.
- The workflow commits `state.json` when availability changes, so repeat alerts
  are suppressed while a configuration remains available. The file contains
  only availability booleans, not personal data or secrets.
- This project is not affiliated with Apple. Pickup availability can change
  between checks, and an alert is not a guarantee that stock remains available.
- For free standard GitHub-hosted runners, keep the repository public. Public
  source code is visible to others; never put the Telegram bot token or chat ID
  in a source file. Keep them in GitHub Actions repository secrets.
