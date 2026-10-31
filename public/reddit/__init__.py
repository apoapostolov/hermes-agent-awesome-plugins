"""Reddit plugin — OAuth login plus the full Reddit API as tools.

Registers twelve tools on the ``reddit`` toolset: login/logout, status, a generic
``reddit_api`` passthrough and curated read/write helpers for subreddits, search,
threads, posts, comments, votes and the inbox.

Login is the published-app authorization-code flow with a loopback catcher on
``http://localhost:8080``; the resulting permanent refresh token is stored in
``$HERMES_HOME/reddit-oauth.json`` and refreshed automatically.
"""

from . import cli, tools as _tools

_HANDLERS = {
    "reddit_setup": _tools.reddit_setup,
    "reddit_login": _tools.reddit_login,
    "reddit_status": _tools.reddit_status,
    "reddit_api": _tools.reddit_api,
    "reddit_subreddit": _tools.reddit_subreddit,
    "reddit_search": _tools.reddit_search,
    "reddit_thread": _tools.reddit_thread,
    "reddit_submit": _tools.reddit_submit,
    "reddit_comment": _tools.reddit_comment,
    "reddit_vote": _tools.reddit_vote,
    "reddit_manage": _tools.reddit_manage,
    "reddit_inbox": _tools.reddit_inbox,
}


def register(ctx):
    for schema in _tools.SCHEMAS:
        name = schema["name"]
        ctx.register_tool(
            name=name,
            toolset="reddit",
            schema=schema,
            handler=_HANDLERS[name],
            description=schema["description"].split(". ")[0],
            emoji="🟠",
            is_async=False,
        )

    ctx.register_cli_command(
        name="reddit",
        help="Reddit login, status, logout and raw API calls",
        setup_fn=cli.setup_parser,
        handler_fn=cli.handle,
        description="Authorize a Reddit account (`hermes reddit login`), inspect the "
        "stored token (`status`), drop it (`logout`), verify app credentials "
        "(`smoke`), or call any endpoint (`api GET /api/v1/me`).",
    )
