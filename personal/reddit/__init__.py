"""Reddit plugin — OAuth login plus the full Reddit API as tools.

Registers tools on the ``reddit`` toolset: login/logout, status, a generic
``reddit_api`` passthrough and curated read/write helpers for subreddits, search,
threads, users, posts, comments, votes and the inbox.

Reads fall back to the app-only ``client_credentials`` token when no account is
linked, so public subreddits, search, threads and user pages work with just the
app configured; writes still require the login.

Login is the published-app authorization-code flow with a loopback catcher on
``http://localhost:8080``; the resulting permanent refresh token is stored in
``$HERMES_HOME/reddit-oauth.json`` and refreshed automatically.
"""

from . import cli, tools as _tools, maintenance

_HANDLERS = {
    "reddit_setup": _tools.reddit_setup,
    "reddit_login": _tools.reddit_login,
    "reddit_status": _tools.reddit_status,
    "reddit_api": _tools.reddit_api,
    "reddit_subreddit": _tools.reddit_subreddit,
    "reddit_search": _tools.reddit_search,
    "reddit_thread": _tools.reddit_thread,
    "reddit_user": _tools.reddit_user,
    "reddit_submit": _tools.reddit_submit,
    "reddit_comment": _tools.reddit_comment,
    "reddit_vote": _tools.reddit_vote,
    "reddit_manage": _tools.reddit_manage,
    "reddit_inbox": _tools.reddit_inbox,
    "reddit_library": _tools.reddit_library,
    "reddit_library_search": _tools.reddit_library_search,
    "reddit_account": _tools.reddit_account,
    "reddit_content": _tools.reddit_content,
    "reddit_community": _tools.reddit_community,
    "reddit_moderation": _tools.reddit_moderation,
    "reddit_messages": _tools.reddit_messages,
    "reddit_wiki": _tools.reddit_wiki,
    "reddit_multis": _tools.reddit_multis,
}


def register(ctx):
    cleanup = maintenance.start()
    on_unload = getattr(ctx, "on_unload", None)
    if cleanup and callable(on_unload):
        on_unload(cleanup)
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
