from datetime import date

import ollama

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


def upcoming() -> str:
    if not cache.is_synced():
        return "YNAB not synced — call ynab_sync() first."

    bills = cache.get_scheduled(within_days=14)
    if not bills:
        return "No scheduled transactions due in the next 14 days."

    lines = ["=== Upcoming Bills (next 14 days) ==="]
    for b in bills:
        lines.append(
            f"  {b['next_date']}  {b['payee_name'] or 'Unknown'}  "
            f"{_fmt(abs(b['amount']))}  [{b['frequency']}]"
            + (f"  — {b['category_name']}" if b['category_name'] else "")
        )
    return "\n".join(lines)


def ask(query: str) -> str:
    if not cache.is_synced():
        return "YNAB not synced — call ynab_sync() first."

    context = _build_context(query)
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "You are a personal finance assistant. Answer the question using ONLY "
                "the budget data below. Do not invent or estimate numbers — if the data "
                "does not contain the answer, say so.\n\n"
                f"Budget data:\n{context}\n\n"
                f"Question: {query}"
            ),
        )
        return resp.response
    except Exception:
        return context


def _build_context(query: str) -> str:
    from datetime import timedelta

    q = query.lower()
    current_month = date.today().strftime("%Y-%m-01")
    parts = []

    # Month summary always included
    summary = cache.get_month_summary(current_month)
    parts.append(
        f"Budget summary ({current_month[:7]}):\n"
        f"  Income: {_fmt(summary['income'])}\n"
        f"  Budgeted: {_fmt(summary['budgeted'])}\n"
        f"  Activity: {_fmt(summary['activity'])}\n"
        f"  Ready to Assign: {_fmt(summary['to_be_budgeted'])}\n"
        f"  Age of Money: {summary['age_of_money']} days"
    )

    # Accounts always included
    accounts = cache.get_accounts()
    if accounts:
        lines = [f"  {a['name']} ({a['type']}): {_fmt(a['balance'])}" for a in accounts]
        parts.append("Account balances:\n" + "\n".join(lines))

    # Categories if budget/spending keywords
    budget_kws = ["budget", "categor", "spend", "left", "remain", "over", "assign",
                  "groceri", "food", "dining", "util", "subscript", "entertain", "how much"]
    if any(kw in q for kw in budget_kws):
        cats = cache.get_categories(current_month)
        if cats:
            lines = [
                f"  {c['group_name']} / {c['name']}: "
                f"budgeted {_fmt(c['budgeted'])}, "
                f"spent {_fmt(abs(c['activity']))}, "
                f"left {_fmt(c['balance'])}"
                for c in cats
            ]
            parts.append("Category budgets this month:\n" + "\n".join(lines))

    # Recent transactions if transaction keywords
    txn_kws = ["transact", "recent", "paid", "bought", "spent at", "purchas", "history", "last month"]
    if any(kw in q for kw in txn_kws):
        since = (date.today() - timedelta(days=30)).isoformat()
        txns = cache.get_transactions(since)[:25]
        if txns:
            lines = [
                f"  {t['date']}  {t['payee_name'] or 'Unknown'} "
                f"[{t['category_name'] or 'Uncategorized'}]: "
                f"{_fmt(abs(t['amount']))}"
                for t in txns
            ]
            parts.append("Recent transactions (last 30 days):\n" + "\n".join(lines))

    return "\n\n".join(parts)
