from . import analysis, tokens, charts, docs, bubblemap, token_details, history, scheduler

analysis_router = analysis.router
tokens_router = tokens.router
charts_router = charts.router
docs_router = docs.router
bubblemap_router = bubblemap.router
token_details_router = token_details.router
history_router = history.router
scheduler_router = scheduler.router

__all__ = [
    "analysis_router",
    "tokens_router",
    "charts_router",
    "docs_router",
    "bubblemap_router",
    "token_details_router",
    "history_router",
    "scheduler_router"
]