from datetime import date

from larvis.agents.ynab import cache, client
from larvis.config import settings


def _fmt(milliunits: int) -> str:
    dollars = milliunits / 1000
    if dollars < 0:
        return f"-${abs(dollars):,.2f}"
    return f"${dollars:,.2f}"


def sync() -> str:
    if not settings.ynab_api_key:
        return "YNAB_API_KEY not configured — add it to .env and restart."
    try:
        result = client.sync_budget(settings.ynab_api_key, settings.ynab_budget_id)
        return (
            f"Synced: {result.accounts} accounts, {result.categories} categories, "
            f"{result.transactions} transactions, {result.scheduled} scheduled."
        )
    except Exception as e:
        return f"Sync failed: {e}"


def status() -> str:
    if not cache.is_synced():
        return "YNAB not synced — call ynab_sync() first."

    current_month = date.today().strftime("%Y-%m-01")
    summary = cache.get_month_summary(current_month)
    accounts = cache.get_accounts()
    categories = cache.get_categories(current_month)

    total_balance = sum(a["balance"] for a in accounts)
    over_budget = sorted(
        [c for c in categories if c["balance"] < 0],
        key=lambda c: c["balance"],
    )

    lines = [
        f"=== Budget Status ({current_month[:7]}) ===",
        f"Ready to Assign:  {_fmt(summary['to_be_budgeted'])}",
        f"Age of Money:     {summary['age_of_money']} days",
        f"On-Budget Total:  {_fmt(total_balance)}",
    ]

    if over_budget:
        lines.append(f"\nOver Budget ({len(over_budget)} categories):")
        for c in over_budget:
            lines.append(f"  {c['group_name']} / {c['name']}: {_fmt(c['balance'])}")
    else:
        lines.append("\nNo categories over budget.")

    return "\n".join(lines)
